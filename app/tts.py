"""
Read the narration aloud: one setting, three backends.

- ``piper``      a local engine (the ``piper-tts`` package) that runs on the CPU, so it
                 never asks the graphics card for memory the story model is using.
- ``openai``     any OpenAI-compatible ``/v1/audio/speech`` endpoint.
- ``elevenlabs`` the ElevenLabs text-to-speech API.

Off by default. The local engine is not a requirement of the app: the player installs
it from the Speech settings, and the chosen voice downloads on first use into
``data/tts-voices/``. Nothing here imports ``piper`` at module level, so the app runs
without the package. Routes in ``app/main.py`` stay thin; this module owns the
configuration row, the preset catalog, text cleaning and chunking, the provider calls
and the install path.
"""
from __future__ import annotations

import copy
import html
import importlib
import importlib.metadata
import io
import json
import math
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.db import connect
from app.gpu_gate import gate_status, gpu_session
from app.turn_dsl import OPCODES

ROOT = Path(__file__).resolve().parent.parent
TTS_CONFIG_KEY = "tts_config"
# The only thing pip ever installs from here; never taken from a request.
PIPER_PACKAGE = "piper-tts==1.8.0"
PIPER_VOICE_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
PIPER_CARD_BASE = "https://huggingface.co/rhasspy/piper-voices/blob/main"
MAX_SPEAK_CHARS = 4000
# Ceilings for a cloud response body: far above any paragraph of mp3, and a probe only needs the status.
SPEAK_READ_LIMIT = 64 * 1024 * 1024
PROBE_READ_LIMIT = 1024 * 1024
PROVIDERS = ("off", "piper", "openai", "elevenlabs")
USER_AGENT = "Morkyn/tts"

PROBE_TIMEOUT_S = 8.0
PIPER_MIN_ONNX_BYTES = 1024 * 1024
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}

MSG_OFF = "Speech is off. Turn it on in Speech settings."
MSG_EMPTY = "Nothing to read: the text is empty once codes and markup are removed."
MSG_NO_KEY = "No API key for the speech service. Enter one in Speech settings or set AI_RPG_TTS_API_KEY"
MSG_ENGINE_MISSING = "The local speech engine is not installed. Open Speech settings and press Install."
MSG_BUSY = (
    "The model or the image engine is using the GPU right now. "
    "Wait for the turn to finish, then press Play again."
)
MSG_SELF_BUSY = "The local speech engine is still busy with the previous paragraph. Press Play again."
MSG_INSTALL_BUSY = "An install is already running. Wait for it to finish."
MSG_INSTALL_STEP = 'Install step must be "all", "engine" or "voice".'
MSG_INSTALL_PROVIDER = 'Install applies to the local engine. Set Provider to "Local (Piper)" and save first.'


class TtsError(RuntimeError):
    """A speech error the route turns into an HTTP status with a plain-sentence detail."""

    status: int = 400

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = int(status)


class TtsOff(TtsError):
    def __init__(self, message: str = MSG_OFF):
        super().__init__(message, 400)


class TtsEmpty(TtsError):
    def __init__(self, message: str = MSG_EMPTY):
        super().__init__(message, 400)


class TtsNotReady(TtsError):
    """Engine, voice or key missing: the player can fix it in Speech settings."""

    def __init__(self, message: str):
        super().__init__(message, 400)


class TtsBusy(TtsError):
    def __init__(self, message: str = MSG_BUSY):
        super().__init__(message, 409)


class TtsUnavailable(TtsError):
    def __init__(self, message: str, http_status: int = 0):
        super().__init__(message, 503)
        self.http_status = int(http_status or 0)


@dataclass
class SpeakResult:
    audio: bytes
    media_type: str
    provider: str
    speed_applied: float
    chars: int


# --- small helpers ---------------------------------------------------------


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is None or not str(value).strip():
        return default
    return str(value).strip()


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(float(raw))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _as_bool(value: Any, *, default: bool = False) -> bool:
    """Strict bool parse: bool('false') is True in Python, which must not enable speech."""
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off", ""}:
        return False
    return default


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _as_speed(value: Any, default: float = 1.0) -> float:
    try:
        speed = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(speed) or math.isinf(speed):
        return default
    return round(_clamp(speed, 0.5, 2.0), 3)


def _as_int(value: Any, default: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _is_loopback(url: str) -> bool:
    try:
        host = urllib.parse.urlparse(url).hostname or ""
    except ValueError:
        return False
    return host.lower() in _LOOPBACK_HOSTS


def normalize_base_url(raw: Any) -> str:
    """``http(s)://host[:port]`` without a trailing slash or ``/v1``; anything else is blank."""
    url = _text(raw, 400)
    if not url:
        return ""
    if not re.match(r"^https?://", url, flags=re.IGNORECASE):
        return ""
    url = url.rstrip("/")
    if url.lower().endswith("/v1"):
        url = url[:-3]
    url = url.rstrip("/")
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        return ""
    if not parsed.hostname:
        return ""
    return url


# --- config ---------------------------------------------------------------


def voice_dir() -> Path:
    """Where Piper voices live. Read per call so tests can point it at a temp dir."""
    raw = _env("AI_RPG_TTS_VOICE_DIR", "")
    if not raw:
        return ROOT / "data" / "tts-voices"
    path = Path(raw).expanduser()
    # A relative value means relative to the repo, not to wherever the server was started.
    return path if path.is_absolute() else ROOT / path


def _base_defaults() -> dict[str, Any]:
    return {
        "provider": "off",
        "enabled": False,
        "preset": "",
        "voice": "",
        "model": "",
        "base_url": "",
        "api_key": "",
        "speed": 1.0,
        "chunk_chars": 0,
        "timeout_seconds": 60,
    }


_ENV_MAP = {
    "provider": "AI_RPG_TTS_PROVIDER",
    "enabled": "AI_RPG_TTS_ENABLED",
    "preset": "AI_RPG_TTS_PRESET",
    "voice": "AI_RPG_TTS_VOICE",
    "model": "AI_RPG_TTS_MODEL",
    "base_url": "AI_RPG_TTS_BASE_URL",
    "api_key": "AI_RPG_TTS_API_KEY",
    "speed": "AI_RPG_TTS_SPEED",
    "chunk_chars": "AI_RPG_TTS_CHUNK_CHARS",
    "timeout_seconds": "AI_RPG_TTS_TIMEOUT",
}


def _apply_env(cfg: dict[str, Any]) -> dict[str, Any]:
    out = dict(cfg)
    for key, env_name in _ENV_MAP.items():
        raw = os.getenv(env_name)
        if raw is None or not str(raw).strip():
            continue
        if key == "enabled":
            out[key] = _as_bool(raw, default=bool(out.get(key)))
        elif key == "speed":
            out[key] = _env_float(env_name, float(out.get(key) or 1.0))
        elif key in {"chunk_chars", "timeout_seconds"}:
            out[key] = _env_int(env_name, int(out.get(key) or 0))
        else:
            out[key] = str(raw).strip()
    return out


def default_tts_config() -> dict[str, Any]:
    """The defaults of the settings row with ``AI_RPG_TTS_*`` applied."""
    return _normalize_tts_config(_apply_env(_base_defaults()))


def normalize_provider(raw: Any) -> str:
    value = str(raw or "").strip().lower()
    aliases = {
        "": "off",
        "off": "off",
        "none": "off",
        "disabled": "off",
        "piper": "piper",
        "local": "piper",
        "openai": "openai",
        "custom": "openai",
        "openai_compatible": "openai",
        "compatible": "openai",
        "elevenlabs": "elevenlabs",
        "eleven": "elevenlabs",
        "11labs": "elevenlabs",
        "eleven_labs": "elevenlabs",
    }
    return aliases.get(value, "off")


def _normalize_tts_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """Aliases, clamps and limits from the config table; unknown keys are dropped."""
    base = _base_defaults()
    out: dict[str, Any] = {}
    provider = normalize_provider(cfg.get("provider"))
    out["provider"] = provider
    out["enabled"] = _as_bool(cfg.get("enabled"), default=False)
    preset = _text(cfg.get("preset"), 80)
    if preset and find_preset(provider, preset) is None:
        preset = ""
    out["preset"] = preset
    out["voice"] = _text(cfg.get("voice"), 120)
    out["model"] = _text(cfg.get("model"), 120)
    out["base_url"] = normalize_base_url(cfg.get("base_url"))
    out["api_key"] = _text(cfg.get("api_key"), 500)
    out["speed"] = _as_speed(cfg.get("speed"), 1.0)
    chunk = _as_int(cfg.get("chunk_chars"), 0)
    out["chunk_chars"] = 0 if chunk <= 0 else int(_clamp(chunk, 200, 4000))
    out["timeout_seconds"] = int(_clamp(_as_int(cfg.get("timeout_seconds"), base["timeout_seconds"]), 5, 300))
    return out


def _read_stored_row() -> dict[str, Any]:
    try:
        with connect() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (TTS_CONFIG_KEY,)).fetchone()
    except Exception:
        return {}
    if not row:
        return {}
    try:
        stored = json.loads(row["value"])
    except (json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(stored, dict):
        return {}
    return {k: v for k, v in stored.items() if k in _base_defaults()}


def get_tts_config() -> dict[str, Any]:
    """The stored row merged over the defaults; ``AI_RPG_TTS_*`` wins when set."""
    merged = {**_base_defaults(), **_read_stored_row()}
    return _normalize_tts_config(_apply_env(merged))


def update_tts_config(payload: dict[str, Any]) -> dict[str, Any]:
    """Partial update: only keys present in ``payload`` change.

    A blank ``api_key`` keeps the stored one. Changing the provider or the preset resets
    voice, model, base_url and chunk_chars (unless the same payload sets them), so a
    voice id never survives a switch to another service.
    """
    stored = {**_base_defaults(), **_read_stored_row()}
    payload = dict(payload or {})
    if "provider" not in payload:
        # The form shows the provider with AI_RPG_TTS_PROVIDER applied and omits it when
        # unchanged; validate the preset (and detect a switch) against that same provider.
        stored["provider"] = normalize_provider(_apply_env(stored).get("provider"))
    next_cfg = dict(stored)
    for key in _base_defaults():
        if key not in payload:
            continue
        value = payload[key]
        if key == "api_key":
            # Empty on POST means "keep existing", so the UI never re-sends secrets.
            if not str(value or "").strip():
                continue
        if value is None:
            continue
        next_cfg[key] = value
    new_provider = normalize_provider(next_cfg.get("provider"))
    old_provider = normalize_provider(stored.get("provider"))
    new_preset = _text(next_cfg.get("preset"), 80)
    if new_preset and find_preset(new_provider, new_preset) is None:
        new_preset = ""
    next_cfg["preset"] = new_preset
    old_preset = _text(stored.get("preset"), 80)
    switched = new_provider != old_provider or ("preset" in payload and new_preset != old_preset)
    if switched:
        for key, blank in (("voice", ""), ("model", ""), ("base_url", ""), ("chunk_chars", 0)):
            if key not in payload or payload.get(key) is None:
                next_cfg[key] = blank
    clean = _normalize_tts_config(next_cfg)
    with connect() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (TTS_CONFIG_KEY, json.dumps(clean, ensure_ascii=True)),
        )
    return public_tts_config(get_tts_config())


def key_env_for(provider: str) -> str:
    provider = normalize_provider(provider)
    if provider == "openai":
        return "OPENAI_API_KEY"
    if provider == "elevenlabs":
        return "ELEVENLABS_API_KEY"
    return ""


def resolve_tts_api_key(cfg: dict[str, Any] | None = None) -> str:
    """Stored key, then ``AI_RPG_TTS_API_KEY``, then the provider's usual variable. Never logged."""
    cfg = cfg or get_tts_config()
    provider = normalize_provider(cfg.get("provider"))
    if provider not in {"openai", "elevenlabs"}:
        return ""
    stored = str(cfg.get("api_key") or "").strip()
    if stored:
        return stored
    names = ["AI_RPG_TTS_API_KEY"]
    if provider == "openai":
        names.append("OPENAI_API_KEY")
    else:
        names.extend(["ELEVENLABS_API_KEY", "ELEVEN_API_KEY"])
    for env_name in names:
        value = os.getenv(env_name)
        if value and str(value).strip():
            return str(value).strip()
    return ""


def resolve_tts_config(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """A copy with the blanks filled from the effective preset, plus what the preset knows."""
    cfg = dict(cfg or get_tts_config())
    provider = normalize_provider(cfg.get("provider"))
    cfg["provider"] = provider
    preset_id = str(cfg.get("preset") or "") or default_preset_id(provider)
    preset = find_preset(provider, preset_id) or {}
    cfg["preset"] = str(preset.get("id") or "")
    cfg["voice"] = str(cfg.get("voice") or "") or str(preset.get("voice") or "")
    cfg["model"] = str(cfg.get("model") or "") or str(preset.get("model") or "")
    cfg["base_url"] = str(cfg.get("base_url") or "") or str(preset.get("base_url") or "")
    chunk = int(cfg.get("chunk_chars") or 0)
    cfg["chunk_chars"] = chunk if chunk > 0 else int(preset.get("chunk_chars") or 1000)
    cfg["sample_rate"] = int(preset.get("sample_rate") or 0)
    cfg["audio_format"] = str(preset.get("audio_format") or "")
    cfg["speed_range"] = list(preset.get("speed_range") or [0.5, 2.0])
    if provider == "elevenlabs":
        cfg["output_format"] = str(preset.get("output_format") or "mp3_44100_128")
    return cfg


def tts_active(cfg: dict[str, Any] | None = None) -> bool:
    cfg = cfg or get_tts_config()
    return bool(cfg.get("enabled")) and normalize_provider(cfg.get("provider")) != "off"


def public_tts_config(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Safe view for the UI: the raw key never leaves the server."""
    cfg = dict(cfg or get_tts_config())
    key = resolve_tts_api_key(cfg)
    resolved = resolve_tts_config(cfg)
    cfg["api_key"] = ""
    cfg["api_key_set"] = bool(key)
    cfg["api_key_hint"] = ("••••" + key[-4:]) if len(key) >= 4 else ("" if not key else "••••")
    cfg["key_env"] = key_env_for(cfg.get("provider"))
    cfg["active"] = tts_active(cfg)
    cfg["resolved"] = {
        "voice": resolved["voice"],
        "model": resolved["model"],
        "base_url": resolved["base_url"],
        "chunk_chars": resolved["chunk_chars"],
        "sample_rate": resolved["sample_rate"],
        "audio_format": resolved["audio_format"],
        "speed_range": resolved["speed_range"],
        "preset": resolved["preset"],
    }
    cfg["voice_dir"] = str(voice_dir().resolve())
    return cfg


def scrub_tts_state(state: Any) -> Any:
    """Blank ``settings.tts_config.api_key`` in a parsed state payload (``/api/state``).

    The settings table is shipped whole to the browser; the speech key must only ever
    travel masked, through ``public_tts_config``. Mutates and returns ``state``.
    """
    settings = state.get("settings") if isinstance(state, dict) else None
    cfg = settings.get(TTS_CONFIG_KEY) if isinstance(settings, dict) else None
    if isinstance(cfg, dict) and cfg.get("api_key"):
        cfg["api_key"] = ""
    return state


def scrub_tts_export(export: Any) -> Any:
    """Drop ``api_key`` from the ``tts_config`` row of an export's settings table.

    An export is meant to be shared; the player re-enters the key after an import.
    Mutates and returns ``export``.
    """
    tables = export.get("tables") if isinstance(export, dict) else None
    rows = tables.get("settings") if isinstance(tables, dict) else None
    if not isinstance(rows, list):
        return export
    for row in rows:
        if not isinstance(row, dict) or str(row.get("key") or "") != TTS_CONFIG_KEY:
            continue
        try:
            value = json.loads(str(row.get("value") or "{}"))
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(value, dict) and value.get("api_key"):
            value["api_key"] = ""
            row["value"] = json.dumps(value, ensure_ascii=True)
    return export


# --- catalog --------------------------------------------------------------

# (code, label, lang, locale, name, quality, speaker, size_mb)
_PIPER_VOICES: tuple[dict[str, Any], ...] = (
    {"code": "en_US-lessac-medium", "label": "English (US) · Lessac · medium", "lang": "en", "locale": "en_US",
     "name": "lessac", "quality": "medium", "speaker": "female", "size_mb": 63},
    {"code": "en_US-amy-medium", "label": "English (US) · Amy · medium", "lang": "en", "locale": "en_US",
     "name": "amy", "quality": "medium", "speaker": "female", "size_mb": 63},
    {"code": "en_US-ryan-high", "label": "English (US) · Ryan · high", "lang": "en", "locale": "en_US",
     "name": "ryan", "quality": "high", "speaker": "male", "size_mb": 115},
    {"code": "en_US-joe-medium", "label": "English (US) · Joe · medium", "lang": "en", "locale": "en_US",
     "name": "joe", "quality": "medium", "speaker": "male", "size_mb": 63},
    {"code": "en_GB-alan-medium", "label": "English (UK) · Alan · medium", "lang": "en", "locale": "en_GB",
     "name": "alan", "quality": "medium", "speaker": "male", "size_mb": 63},
    {"code": "en_GB-alba-medium", "label": "English (UK) · Alba · medium", "lang": "en", "locale": "en_GB",
     "name": "alba", "quality": "medium", "speaker": "female", "size_mb": 63},
)
_OPENAI_VOICES: tuple[str, ...] = ("alloy", "ash", "coral", "echo", "fable", "onyx", "nova", "sage", "shimmer")
_ELEVEN_VOICES: tuple[tuple[str, str], ...] = (
    ("21m00Tcm4TlvDq8ikWAM", "Rachel"),
    ("pNInz6obpgDQGcFmaJgB", "Adam"),
    ("EXAVITQu4vr4xnSDxMaL", "Bella"),
    ("ErXwobaYiN019PkySvjV", "Antoni"),
    ("JBFqnCBsd6RMkjVDRZzo", "George"),
)
_PIPER_CODE_RE = re.compile(r"[a-z]{2}_[A-Z]{2}-[a-z0-9_]+-(x_low|low|medium|high)")

_DEFAULT_PRESET = {
    "piper": "en_US-lessac-medium",
    "openai": "openai_gpt4o_mini_tts",
    "elevenlabs": "elevenlabs_multilingual_v2",
}


def _piper_voice_row(code: str) -> dict[str, Any] | None:
    for row in _PIPER_VOICES:
        if row["code"] == code:
            return row
    return None


def piper_voice_files(code: str) -> list[dict[str, str]]:
    """The two files of a catalog voice: ``[{name, url}]``. Empty for an unknown code."""
    row = _piper_voice_row(code)
    if row is None:
        return []
    folder = f"{PIPER_VOICE_BASE}/{row['lang']}/{row['locale']}/{row['name']}/{row['quality']}"
    return [
        {"name": f"{code}.onnx", "url": f"{folder}/{code}.onnx?download=true"},
        {"name": f"{code}.onnx.json", "url": f"{folder}/{code}.onnx.json?download=true"},
    ]


def _piper_presets() -> list[dict[str, Any]]:
    out = []
    for row in _PIPER_VOICES:
        code = row["code"]
        out.append({
            "id": code,
            "label": row["label"],
            "provider": "piper",
            "voice": code,
            "model": "",
            "base_url": "",
            "language": row["locale"],
            "quality": row["quality"],
            "speaker": row["speaker"],
            "sample_rate": 22050,
            "speed": 1.0,
            "speed_range": [0.5, 2.0],
            "chunk_chars": 600,
            "audio_format": "wav",
            "size_mb": row["size_mb"],
            "voices": [],
            "model_card": f"{PIPER_CARD_BASE}/{row['lang']}/{row['locale']}/{row['name']}/{row['quality']}/MODEL_CARD",
            "files": piper_voice_files(code),
        })
    return out


def _openai_presets() -> list[dict[str, Any]]:
    voices = [{"id": v, "label": v.capitalize()} for v in _OPENAI_VOICES]
    common = {
        "provider": "openai",
        "sample_rate": 24000,
        "speed": 1.0,
        "speed_range": [0.25, 4.0],
        "audio_format": "mp3",
    }
    return [
        {**common, "id": "openai_gpt4o_mini_tts", "label": "OpenAI · gpt-4o-mini-tts",
         "base_url": "https://api.openai.com", "model": "gpt-4o-mini-tts", "voice": "coral",
         "chunk_chars": 4000, "key_env": "OPENAI_API_KEY", "custom_url": False, "voices": voices},
        {**common, "id": "openai_tts1", "label": "OpenAI · tts-1",
         "base_url": "https://api.openai.com", "model": "tts-1", "voice": "onyx",
         "chunk_chars": 4000, "key_env": "OPENAI_API_KEY", "custom_url": False, "voices": voices},
        {**common, "id": "openai_compatible", "label": "Custom OpenAI-compatible URL",
         "base_url": "http://127.0.0.1:8880", "model": "tts-1", "voice": "",
         "chunk_chars": 1000, "key_env": "AI_RPG_TTS_API_KEY", "custom_url": True, "voices": []},
    ]


def _elevenlabs_presets() -> list[dict[str, Any]]:
    voices = [{"id": vid, "label": label} for vid, label in _ELEVEN_VOICES]
    common = {
        "provider": "elevenlabs",
        "base_url": "https://api.elevenlabs.io",
        "voice": _ELEVEN_VOICES[0][0],
        "sample_rate": 44100,
        "speed": 1.0,
        "speed_range": [0.7, 1.2],
        "chunk_chars": 4000,
        "audio_format": "mp3",
        "output_format": "mp3_44100_128",
        "key_env": "ELEVENLABS_API_KEY",
        "voices": voices,
    }
    return [
        {**common, "id": "elevenlabs_multilingual_v2", "label": "ElevenLabs · Multilingual v2 (quality)",
         "model": "eleven_multilingual_v2"},
        {**common, "id": "elevenlabs_turbo_v2_5", "label": "ElevenLabs · Turbo v2.5 (fast)",
         "model": "eleven_turbo_v2_5"},
        {**common, "id": "elevenlabs_flash_v2_5", "label": "ElevenLabs · Flash v2.5 (fastest)",
         "model": "eleven_flash_v2_5"},
    ]


def tts_catalog() -> dict[str, Any]:
    """Providers and their known-good presets. Static; built fresh so callers may mutate it."""
    return copy.deepcopy({
        "providers": [
            {"id": "off", "label": "Off", "kind": "none", "needs_key": False, "audio_format": ""},
            {"id": "piper", "label": "Local (Piper, runs on the CPU)", "kind": "local", "needs_key": False,
             "audio_format": "wav"},
            {"id": "openai", "label": "OpenAI-compatible API", "kind": "cloud", "needs_key": True,
             "audio_format": "mp3"},
            {"id": "elevenlabs", "label": "ElevenLabs", "kind": "cloud", "needs_key": True, "audio_format": "mp3"},
        ],
        "default_preset": dict(_DEFAULT_PRESET),
        "presets": {
            "piper": _piper_presets(),
            "openai": _openai_presets(),
            "elevenlabs": _elevenlabs_presets(),
        },
    })


def find_preset(provider: str, preset_id: str) -> dict[str, Any] | None:
    provider = normalize_provider(provider)
    preset_id = str(preset_id or "").strip()
    if not preset_id or provider == "off":
        return None
    builders = {"piper": _piper_presets, "openai": _openai_presets, "elevenlabs": _elevenlabs_presets}
    builder = builders.get(provider)
    if builder is None:
        return None
    for preset in builder():
        if preset["id"] == preset_id:
            return preset
    return None


def default_preset_id(provider: str) -> str:
    return _DEFAULT_PRESET.get(normalize_provider(provider), "")


# --- text -----------------------------------------------------------------

_CODE_BLOCK_RE = re.compile(r"\[\[\s*[A-Za-z]{1,3}\d{0,4}\s*\]\]")  # [[A]] [[L1]] [[N12]]
_BARE_CODE_RE = re.compile(r"(?<![\w'])[A-Z]{1,2}\d{1,4}(?![\w'])")  # L1 I2 E3 N4 Q5
_HTML_TAG_RE = re.compile(r"<[^>\n]{1,200}>")
_HTML_BLOCK_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1\s*>", re.IGNORECASE | re.DOTALL)
# Comment, debug and marker lines; headings are "#" plus a space ("#3 on the list" is prose).
_DSL_LINE_RE = re.compile(r"^\s*(?:#{1,6}\s|//|>>|@[A-Z]{2,}\b|DEBUG\b|TRACE\b|(?i:\[debug\]|\[trace\]))")
# A line's first word and what follows it, for the opcode rule in _is_dsl_line.
_LINE_HEAD_RE = re.compile(r"^\s*([A-Z][A-Z_]{2,})(?:\s+(\S+))?")
# An op word glued to a code mid-line ("... creaks. MOVE L2"): the line rule above only
# catches ops at the start of a line, so the pair goes here, before bare codes.
_INLINE_OP_RE = re.compile(r"(?<![\w'])[A-Z][A-Z_]{2,}\s+[A-Z]{1,2}\d{1,4}(?![\w'])")
_MD_LINK_RE = re.compile(r"\[([^\]\n]{1,200})\]\((?:https?://|/)[^)\s]{1,500}\)")
_URL_RE = re.compile(r"https?://[^\s<>\"']+")
_MD_STRONG_RE = re.compile(r"\*\*|__|~~|`+")
_MD_EM_OPEN_RE = re.compile(r"(?<!\w)[*_]+(?=\S)")
_MD_EM_CLOSE_RE = re.compile(r"(?<=\S)[*_]+(?!\w)")
_MD_LINE_MARK_RE = re.compile(r"^\s*(?:#{1,6}|>+|[-*•]|\d{1,2}[.)])\s+")


def _is_dsl_line(line: str) -> bool:
    """A line that is a DSL op, JSON, or a comment/debug line rather than prose.

    Only a real opcode (``MOVE L2``, ``QUEST_DONE Q1``) or an all-caps word followed
    by a code or a quoted argument counts as an op: "YOU are the one the prophecy
    named." and "WAIT here, she said." are prose and stay.
    """
    if _DSL_LINE_RE.match(line):
        return True
    stripped = line.strip()
    if stripped in {"{", "}", "[", "]"}:
        return True
    if stripped.startswith("{") and stripped.rstrip(",").endswith("}"):
        return True
    if stripped.startswith("[") and stripped.rstrip(",").endswith("]") and ('"' in stripped or "{" in stripped):
        return True
    head = _LINE_HEAD_RE.match(line)
    if not head:
        return False
    word, arg = head.group(1), head.group(2) or ""
    if word in OPCODES:
        return True
    return bool(arg) and (arg.startswith('"') or _BARE_CODE_RE.fullmatch(arg) is not None)


def clean_text(text: str) -> str:
    """The narration as it should be spoken: no codes, markup or debug lines.

    Returns ``""`` when nothing readable is left.
    """
    raw = str(text or "")
    if not raw.strip():
        return ""
    out = html.unescape(raw)
    out = _HTML_BLOCK_RE.sub(" ", out)
    out = _HTML_TAG_RE.sub("", out)
    # Codes go first so a paragraph that starts with "[[L1]]" is not mistaken for a
    # bracket line and dropped whole.
    out = _CODE_BLOCK_RE.sub(" ", out)
    lines = []
    for line in out.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if _is_dsl_line(line):
            continue
        lines.append(line)
    out = "\n".join(lines)
    out = _INLINE_OP_RE.sub(" ", out)
    out = _BARE_CODE_RE.sub(" ", out)
    out = _MD_LINK_RE.sub(r"\1", out)
    out = _URL_RE.sub(" ", out)
    out = _MD_STRONG_RE.sub("", out)
    out = _MD_EM_OPEN_RE.sub("", out)
    out = _MD_EM_CLOSE_RE.sub("", out)
    out = "\n".join(_MD_LINE_MARK_RE.sub("", line) for line in out.split("\n"))
    out = out.replace("…", "...")
    out = re.sub(r"[^\S\n]+", " ", out)
    # A removed code leaves "waited at ." behind; close the gap.
    out = re.sub(r" +([.,;:!?])", r"\1", out)
    out = re.sub(r" *\n *", "\n", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    out = out.strip()
    if not re.search(r"\w", out):
        return ""
    return out


def split_paragraphs(text: str, *, max_paragraphs: int = 60) -> list[str]:
    """Cleaned paragraphs in order (split on newlines, like ``paragraphs()`` in the UI)."""
    cleaned = clean_text(text)
    if not cleaned:
        return []
    parts = [p.strip() for p in re.split(r"\n+", cleaned)]
    out = [p for p in parts if p]
    return out[: max(1, int(max_paragraphs))]


_SENTENCE_END_RE = re.compile(r"(?<=[.!?…])[\"'”’)\]]*\s+")
_CLAUSE_END_RE = re.compile(r"(?<=[;:,])\s+")


def _split_at(text: str, pattern: re.Pattern[str]) -> list[str]:
    pieces: list[str] = []
    start = 0
    for match in pattern.finditer(text):
        piece = text[start:match.end()].strip()
        if piece:
            pieces.append(piece)
        start = match.end()
    tail = text[start:].strip()
    if tail:
        pieces.append(tail)
    return pieces


def _units_under(text: str, limit: int) -> list[str]:
    """Pieces of ``text`` no longer than ``limit``: sentences, then clauses, words, hard cuts."""
    out: list[str] = []
    for sentence in _split_at(text, _SENTENCE_END_RE):
        if len(sentence) <= limit:
            out.append(sentence)
            continue
        for clause in _split_at(sentence, _CLAUSE_END_RE):
            if len(clause) <= limit:
                out.append(clause)
                continue
            current = ""
            for word in clause.split(" "):
                if not word:
                    continue
                while len(word) > limit:
                    if current:
                        out.append(current)
                        current = ""
                    out.append(word[:limit])
                    word = word[limit:]
                if not word:
                    continue
                if not current:
                    current = word
                elif len(current) + 1 + len(word) <= limit:
                    current = f"{current} {word}"
                else:
                    out.append(current)
                    current = word
            if current:
                out.append(current)
    return out


def chunk_text(text: str, limit: int) -> list[str]:
    """Split a paragraph into request-sized chunks, preferring sentence ends. Order kept."""
    limit = int(_clamp(_as_int(limit, 1000), 200, 4000))
    flat = " ".join(str(text or "").split())
    if not flat:
        return []
    if len(flat) <= limit:
        return [flat]
    chunks: list[str] = []
    current = ""
    for unit in _units_under(flat, limit):
        if not current:
            current = unit
        elif len(current) + 1 + len(unit) <= limit:
            current = f"{current} {unit}"
        else:
            chunks.append(current)
            current = unit
    if current:
        chunks.append(current)
    return [c for c in chunks if c]


# --- providers ------------------------------------------------------------


def _http(req: urllib.request.Request, timeout: float, *, limit: int = SPEAK_READ_LIMIT) -> tuple[bytes, dict[str, str]]:
    """The one ``urlopen`` call for cloud requests. Network trouble becomes a 503 sentence.

    The body is read in pieces up to ``limit`` bytes: the timeout is per socket read, so
    a misconfigured server that keeps sending would otherwise fill memory unchecked.
    """
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            parts: list[bytes] = []
            total = 0
            while True:
                piece = response.read(256 * 1024)
                if not piece:
                    break
                total += len(piece)
                if total > limit:
                    raise TtsUnavailable("The speech service sent more data than a paragraph of audio can be.")
                parts.append(piece)
            headers = {str(k): str(v) for k, v in response.headers.items()}
            return b"".join(parts), headers
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read()
        except Exception:
            body = b""
        snippet = " ".join(body.decode("utf-8", errors="replace").split())[:200]
        raise TtsUnavailable(
            f"The speech service refused the request (HTTP {exc.code}): {snippet}", http_status=exc.code
        ) from exc
    except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
        reason = getattr(exc, "reason", None) or exc
        raise TtsUnavailable(f"The speech service did not answer: {reason}") from exc


def _require_key(cfg: dict[str, Any]) -> str:
    """The resolved key, or a 400 when a non-local cloud host has none."""
    key = resolve_tts_api_key(cfg)
    if key:
        return key
    provider = normalize_provider(cfg.get("provider"))
    if provider == "openai" and _is_loopback(str(cfg.get("base_url") or "")):
        return ""
    extra = key_env_for(provider)
    raise TtsNotReady(MSG_NO_KEY + (f" or {extra}." if extra else "."))


def build_openai_request(cfg: dict[str, Any], text: str, *, voice: str, speed: float) -> tuple[str, dict[str, str], bytes]:
    base_url = normalize_base_url(cfg.get("base_url")) or str(cfg.get("base_url") or "").rstrip("/")
    url = f"{base_url}/v1/audio/speech"
    headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
    key = resolve_tts_api_key(cfg)
    if key:
        headers["Authorization"] = f"Bearer {key}"
    body = {
        "model": str(cfg.get("model") or ""),
        "input": text,
        "voice": voice,
        "speed": round(float(speed), 3),
        "response_format": "mp3",
    }
    return url, headers, json.dumps(body, ensure_ascii=False).encode("utf-8")


def build_elevenlabs_request(cfg: dict[str, Any], text: str, *, voice: str, speed: float) -> tuple[str, dict[str, str], bytes]:
    base_url = normalize_base_url(cfg.get("base_url")) or "https://api.elevenlabs.io"
    output_format = str(cfg.get("output_format") or "mp3_44100_128")
    url = f"{base_url}/v1/text-to-speech/{urllib.parse.quote(voice, safe='')}?output_format={urllib.parse.quote(output_format, safe='')}"
    headers = {
        "xi-api-key": resolve_tts_api_key(cfg),
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
        "User-Agent": USER_AGENT,
    }
    body = {
        "text": text,
        "model_id": str(cfg.get("model") or ""),
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "speed": _eleven_speed(speed),
        },
    }
    return url, headers, json.dumps(body, ensure_ascii=False).encode("utf-8")


def _eleven_speed(speed: float) -> float:
    return round(_clamp(float(speed), 0.7, 1.2), 3)


def _join_audio(parts: list[bytes], fmt: str) -> bytes:
    parts = [p for p in parts if p]
    if not parts:
        return b""
    if len(parts) == 1:
        return parts[0]
    if fmt != "wav":
        # MPEG frame streams play through when concatenated.
        return b"".join(parts)
    frames: list[bytes] = []
    params = None
    for part in parts:
        with wave.open(io.BytesIO(part), "rb") as wf:
            if params is None:
                params = wf.getparams()
            frames.append(wf.readframes(wf.getnframes()))
    if params is None:
        return b""
    return _wav_bytes(b"".join(frames), params.framerate, channels=params.nchannels, width=params.sampwidth)


def _wav_bytes(pcm: bytes, sample_rate: int, *, channels: int = 1, width: int = 2) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(width)
        wf.setframerate(int(sample_rate))
        wf.writeframes(pcm)
    return buf.getvalue()


def speak_openai(cfg: dict[str, Any], text: str, *, voice: str, speed: float) -> SpeakResult:
    _require_key(cfg)
    timeout = float(cfg.get("timeout_seconds") or 60)
    parts: list[bytes] = []
    for chunk in chunk_text(text, int(cfg.get("chunk_chars") or 4000)):
        url, headers, data = build_openai_request(cfg, chunk, voice=voice, speed=speed)
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        body, _ = _http(req, timeout)
        parts.append(body)
    return SpeakResult(_join_audio(parts, "mp3"), "audio/mpeg", "openai", float(speed), len(text))


def speak_elevenlabs(cfg: dict[str, Any], text: str, *, voice: str, speed: float) -> SpeakResult:
    _require_key(cfg)
    timeout = float(cfg.get("timeout_seconds") or 60)
    parts: list[bytes] = []
    for chunk in chunk_text(text, int(cfg.get("chunk_chars") or 4000)):
        url, headers, data = build_elevenlabs_request(cfg, chunk, voice=voice, speed=speed)
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        body, _ = _http(req, timeout)
        parts.append(body)
    return SpeakResult(_join_audio(parts, "mp3"), "audio/mpeg", "elevenlabs", _eleven_speed(speed), len(text))


def _synthesize_piper(cfg: dict[str, Any], text: str, *, voice: str, speed: float) -> SpeakResult:
    piper = _import_piper()
    if piper is None:
        raise TtsNotReady(MSG_ENGINE_MISSING)
    loaded = load_piper_voice(voice)
    try:
        syn = piper.SynthesisConfig(length_scale=1.0 / float(speed))
        sample_rate = int(getattr(getattr(loaded, "config", None), "sample_rate", 0) or 22050)
        pcm = bytearray()
        for chunk in chunk_text(text, int(cfg.get("chunk_chars") or 600)):
            for audio_chunk in loaded.synthesize(chunk, syn):
                pcm.extend(bytes(audio_chunk.audio_int16_bytes))
    except TtsError:
        raise
    except Exception as exc:
        raise TtsUnavailable(f"The local speech engine failed: {str(exc)[:300]}") from exc
    return SpeakResult(_wav_bytes(bytes(pcm), sample_rate), "audio/wav", "piper", float(speed), len(text))


def _gate_rivals() -> list[str]:
    """Job types other than speech that hold the GPU gate right now."""
    try:
        active = gate_status().get("active") or {}
    except Exception:
        active = {}
    return sorted(str(key) for key in active if key != "tts")


def speak_piper(cfg: dict[str, Any], text: str, *, voice: str, speed: float) -> SpeakResult:
    """Local synthesis behind the GPU gate.

    A turn or an image job holding the gate answers 409 at once and never queues. An
    earlier speak request (one the client abandoned with Stop, or a second tab) is
    waited for instead, up to the configured timeout, so Stop-then-Play does not
    bounce off our own gate with the wrong message.
    """
    deadline = time.monotonic() + float(cfg.get("timeout_seconds") or 60)
    while True:
        if _gate_rivals():
            raise TtsBusy()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TtsUnavailable(MSG_SELF_BUSY)
        try:
            # Short waits: every two seconds the loop checks again whether a turn or an
            # image job took the gate meanwhile, and answers 409 if so.
            with gpu_session("tts", wait=True, timeout=min(2.0, remaining)):
                return _synthesize_piper(cfg, text, voice=voice, speed=speed)
        except TtsError:
            raise
        except TimeoutError:
            continue
        except RuntimeError as exc:
            # Only the gate raises a bare RuntimeError here; engine errors were mapped above.
            raise TtsBusy() from exc


def speak_bytes(text: str, *, voice: str = "", speed: float | None = None) -> SpeakResult:
    """One paragraph (or selection) to audio bytes, using the configured provider."""
    cfg = resolve_tts_config()
    if not tts_active(cfg):
        raise TtsOff()
    cleaned = " ".join(clean_text(text).split())
    if not cleaned:
        raise TtsEmpty()
    if len(cleaned) > MAX_SPEAK_CHARS:
        raise TtsError(f"Text is longer than {MAX_SPEAK_CHARS} characters. Send one paragraph at a time.", 400)
    chosen_voice = _text(voice, 120) or str(cfg.get("voice") or "")
    chosen_speed = _as_speed(speed if speed is not None else cfg.get("speed"), 1.0)
    provider = cfg["provider"]
    if provider == "piper":
        result = speak_piper(cfg, cleaned, voice=chosen_voice, speed=chosen_speed)
    elif provider == "openai":
        if not chosen_voice:
            raise TtsNotReady("No voice is set. Pick or type a voice in Speech settings.")
        result = speak_openai(cfg, cleaned, voice=chosen_voice, speed=chosen_speed)
    elif provider == "elevenlabs":
        if not chosen_voice:
            raise TtsNotReady("No voice is set. Pick a voice in Speech settings.")
        result = speak_elevenlabs(cfg, cleaned, voice=chosen_voice, speed=chosen_speed)
    else:
        raise TtsOff()
    result.chars = len(cleaned)
    return result


# --- piper install / load -------------------------------------------------

_piper_voice_cache: dict[str, Any] = {}
_piper_lock = threading.Lock()
# One install at a time: two presses (two tabs) must never write the same .partial file.
_install_lock = threading.Lock()


def _import_piper():
    try:
        return importlib.import_module("piper")
    except ImportError:
        return None
    except Exception:
        # A broken install (missing native library) must read as "not installed", not a stack trace.
        return None


def piper_installed() -> tuple[bool, str]:
    if _import_piper() is None:
        return False, ""
    try:
        return True, str(importlib.metadata.version("piper-tts"))
    except Exception:
        return True, ""


def _valid_piper_code(code: str) -> bool:
    """A catalog code, or a code that already sits on disk and looks like a Piper voice."""
    code = str(code or "").strip()
    if not code or len(code) > 120:
        return False
    if _piper_voice_row(code) is not None:
        return True
    if _PIPER_CODE_RE.fullmatch(code) is None:
        return False
    onnx, _ = piper_voice_paths(code)
    return onnx.is_file()


def piper_voice_paths(code: str) -> tuple[Path, Path]:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "", str(code or ""))[:120]
    base = voice_dir()
    return base / f"{safe}.onnx", base / f"{safe}.onnx.json"


def piper_voice_present(code: str) -> bool:
    onnx, meta = piper_voice_paths(code)
    try:
        return onnx.is_file() and onnx.stat().st_size > PIPER_MIN_ONNX_BYTES and meta.is_file() and meta.stat().st_size > 0
    except OSError:
        return False


def _check_voice_code(code: str) -> str:
    code = str(code or "").strip()
    if not _valid_piper_code(code):
        raise TtsNotReady(f'Unknown voice "{code}". Pick one from the list in Speech settings.')
    return code


def load_piper_voice(code: str):
    """The loaded ``PiperVoice`` for a code, cached. Clear errors when something is missing."""
    code = _check_voice_code(code)
    piper = _import_piper()
    if piper is None:
        raise TtsNotReady(MSG_ENGINE_MISSING)
    if not piper_voice_present(code):
        raise TtsNotReady(f"The voice {code} is not downloaded yet. Open Speech settings and press Install.")
    with _piper_lock:
        cached = _piper_voice_cache.get(code)
        if cached is not None:
            return cached
        onnx, meta = piper_voice_paths(code)
        try:
            loaded = piper.PiperVoice.load(str(onnx), config_path=str(meta))
        except Exception as exc:
            detail = f"The local speech engine failed: {str(exc)[:300]}"
            if _piper_voice_row(code) is not None:
                # A catalog voice that does not load is a broken download; remove it so
                # the next Install fetches it again instead of reporting "already".
                _remove_voice_files(code)
                detail += " The voice files were removed; open Speech settings and press Install to download them again."
            raise TtsUnavailable(detail) from exc
        _piper_voice_cache[code] = loaded
        return loaded


def pip_install_piper(*, timeout: float = 900.0) -> dict[str, Any]:
    """Install the pinned package into this interpreter. Never runs through a shell."""
    env = {**os.environ, "PIP_DISABLE_PIP_VERSION_CHECK": "1", "PIP_NO_INPUT": "1"}
    argv = [sys.executable, "-m", "pip", "install", PIPER_PACKAGE, "--prefer-binary"]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False, env=env)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"pip did not finish within {int(timeout)} seconds."}
    except OSError as exc:
        return {"ok": False, "error": str(exc)[:600]}
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "pip failed").strip()[-600:]
        return {"ok": False, "error": tail}
    importlib.invalidate_caches()
    sys.modules.pop("piper", None)
    ok, version = piper_installed()
    if not ok:
        return {"ok": False, "error": "pip finished but the package cannot be imported. Restart the server and try again."}
    return {"ok": True, "version": version}


def _fetch_to_file(url: str, dest: Path, *, timeout: float) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".partial")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method="GET")
    total = 0
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            try:
                expected = int(str(resp.headers.get("Content-Length") or 0).strip() or 0)
            except (TypeError, ValueError, AttributeError):
                expected = 0
            with open(tmp, "wb") as fh:
                while True:
                    chunk = resp.read(1024 * 256)
                    if not chunk:
                        break
                    fh.write(chunk)
                    total += len(chunk)
        if expected and total != expected:
            # A stream that closed early is not a voice; keep nothing of it.
            raise TtsUnavailable(f"the download stopped at {_mb(total)} of {_mb(expected)}")
        tmp.replace(dest)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    return total


def _remove_voice_files(code: str) -> None:
    for path in piper_voice_paths(code):
        try:
            path.unlink()
        except OSError:
            pass


def download_piper_voice(code: str, *, timeout: float = 600.0) -> dict[str, Any]:
    """Fetch the two files of a catalog voice into ``voice_dir()``; verify they are a Piper voice."""
    code = str(code or "").strip()
    files = piper_voice_files(code)
    if not files:
        raise TtsNotReady(f'Unknown voice "{code}". Pick one from the list in Speech settings.')
    onnx, meta = piper_voice_paths(code)
    if piper_voice_present(code):
        return {"ok": True, "already": True, "path": str(onnx), "bytes": onnx.stat().st_size}
    total = 0
    for entry in files:
        dest = voice_dir() / entry["name"]
        if dest.is_file() and dest.stat().st_size > 0:
            total += dest.stat().st_size
            continue
        try:
            total += _fetch_to_file(entry["url"], dest, timeout=timeout)
        except TtsUnavailable as exc:
            raise TtsUnavailable(f"Could not download the voice {code}: {exc}") from exc
        except urllib.error.HTTPError as exc:
            raise TtsUnavailable(f"Could not download the voice {code}: HTTP {exc.code}") from exc
        except (urllib.error.URLError, socket.timeout, TimeoutError, OSError) as exc:
            reason = getattr(exc, "reason", None) or exc
            raise TtsUnavailable(f"Could not download the voice {code}: {reason}") from exc
    try:
        info = json.loads(meta.read_text(encoding="utf-8"))
        sample_rate = int((info.get("audio") or {}).get("sample_rate") or 0) if isinstance(info, dict) else 0
        onnx_ok = onnx.is_file() and onnx.stat().st_size > PIPER_MIN_ONNX_BYTES
    except (OSError, ValueError, TypeError, AttributeError):
        sample_rate, onnx_ok = 0, False
    if sample_rate <= 0 or not onnx_ok:
        _remove_voice_files(code)
        raise TtsUnavailable(f"Could not download the voice {code}: file is not a Piper voice")
    _piper_voice_cache.pop(code, None)
    return {"ok": True, "already": False, "path": str(onnx), "bytes": onnx.stat().st_size + meta.stat().st_size}


def _mb(num: int) -> str:
    return f"{num / (1024 * 1024):.1f} MB"


def install_piper(*, what: str = "all", voice: str = "") -> dict[str, Any]:
    """Install the engine and/or download the voice. Idempotent: a second press reports ``already``."""
    what = str(what or "all").strip().lower()
    if what not in {"all", "engine", "voice"}:
        raise TtsError(MSG_INSTALL_STEP, 400)
    cfg = resolve_tts_config()
    if cfg["provider"] != "piper":
        raise TtsError(MSG_INSTALL_PROVIDER, 400)
    code = _text(voice, 120) or str(cfg.get("voice") or "")
    if _piper_voice_row(code) is None:
        raise TtsError(f'Unknown voice "{code}". Pick one from the list in Speech settings.', 400)
    if not _install_lock.acquire(blocking=False):
        raise TtsBusy(MSG_INSTALL_BUSY)
    try:
        return _install_piper_steps(what, code)
    finally:
        _install_lock.release()


def _install_piper_steps(what: str, code: str) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    if what in {"all", "engine"}:
        started = time.monotonic()
        ok, version = piper_installed()
        if ok:
            steps.append({"step": "engine", "status": "already", "detail": f"piper-tts {version}".strip(), "seconds": 0.0})
        else:
            result = pip_install_piper()
            if not result.get("ok"):
                raise TtsUnavailable(f"Could not install the speech engine: {result.get('error') or 'pip failed'}")
            steps.append({
                "step": "engine",
                "status": "installed",
                "detail": f"piper-tts {result.get('version') or ''}".strip(),
                "seconds": round(time.monotonic() - started, 1),
            })
    else:
        steps.append({"step": "engine", "status": "skipped", "detail": "", "seconds": 0.0})
    if what in {"all", "voice"}:
        result = download_piper_voice(code)
        steps.append({
            "step": "voice",
            "status": "already" if result.get("already") else "installed",
            "detail": f"{code} ({_mb(int(result.get('bytes') or 0))})",
            "path": result.get("path") or "",
            "bytes": int(result.get("bytes") or 0),
        })
    else:
        steps.append({"step": "voice", "status": "skipped", "detail": "", "path": "", "bytes": 0})
    return {"ok": True, "steps": steps, "status": probe_tts()}


def _provider_label(provider: str) -> str:
    """The short name the probe's "Ready:" line uses; the catalog label carries the explanation."""
    if provider == "piper":
        return "Piper"
    for row in tts_catalog()["providers"]:
        if row["id"] == provider:
            return str(row["label"])
    return provider


def probe_tts(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Is speech ready? Never raises for a failed probe; ``detail`` says what is missing."""
    cfg = resolve_tts_config(cfg)
    provider = cfg["provider"]
    status: dict[str, Any] = {
        "ok": False,
        "provider": provider,
        "enabled": bool(cfg.get("enabled")),
        "active": tts_active(cfg),
        "configured": False,
        "key_set": None,
        "engine_installed": None,
        "engine_version": "",
        "voice_downloaded": None,
        "voice_path": "",
        "reachable": False,
        "gate": {},
        "detail": "",
    }
    try:
        gate = gate_status()
        status["gate"] = {"active": gate.get("active") or {}, "allow_parallel_now": bool(gate.get("allow_parallel_now"))}
    except Exception:
        status["gate"] = {"active": {}, "allow_parallel_now": False}
    voice = str(cfg.get("voice") or "")
    model = str(cfg.get("model") or "")
    if provider == "off":
        status["detail"] = "Speech is off. Pick a provider in Speech settings to read the story aloud."
        return status
    status["configured"] = bool(voice) and (provider == "piper" or bool(model))
    label = _provider_label(provider)
    not_enabled = "" if status["enabled"] else ' Speech is still off: tick "Read narration aloud" and save.'
    if provider == "piper":
        installed, version = piper_installed()
        status["engine_installed"] = installed
        status["engine_version"] = version
        if voice:
            onnx, _ = piper_voice_paths(voice)
            status["voice_path"] = str(onnx)
            status["voice_downloaded"] = piper_voice_present(voice)
        else:
            status["voice_downloaded"] = False
        if not installed:
            status["detail"] = MSG_ENGINE_MISSING
            return status
        if not voice:
            status["detail"] = "No voice is set. Pick one from the list in Speech settings."
            return status
        if not status["voice_downloaded"]:
            status["detail"] = f"The voice {voice} is not downloaded yet. Open Speech settings and press Install."
            return status
        try:
            load_piper_voice(voice)
        except TtsError as exc:
            status["detail"] = str(exc)
            return status
        status["reachable"] = True
        status["ok"] = True
        status["detail"] = f"Ready: {label}, {voice}.{not_enabled}"
        return status
    # Cloud providers.
    key = resolve_tts_api_key(cfg)
    status["key_set"] = bool(key)
    base_url = str(cfg.get("base_url") or "")
    if not status["configured"]:
        status["detail"] = "No voice or model is set. Pick a preset in Speech settings."
        return status
    if not key and not (provider == "openai" and _is_loopback(base_url)):
        extra = key_env_for(provider)
        status["detail"] = MSG_NO_KEY + (f" or {extra}." if extra else ".")
        return status
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if provider == "openai":
        url = f"{base_url}/v1/models"
        if key:
            headers["Authorization"] = f"Bearer {key}"
    else:
        url = f"{base_url}/v1/user"
        headers["xi-api-key"] = key
    try:
        _http(urllib.request.Request(url, headers=headers, method="GET"), PROBE_TIMEOUT_S, limit=PROBE_READ_LIMIT)
    except TtsUnavailable as exc:
        if provider == "elevenlabs" and exc.http_status == 401:
            status["detail"] = "ElevenLabs refused the API key."
        elif exc.http_status == 401:
            status["detail"] = "The speech service refused the API key."
        else:
            status["detail"] = str(exc)
        return status
    status["reachable"] = True
    status["ok"] = True
    status["detail"] = f"Ready: {label}, {model}, voice {voice}.{not_enabled}"
    return status
