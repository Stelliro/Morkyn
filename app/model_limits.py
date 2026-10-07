"""Token limits that follow the model, with a per-model override the player can keep.

Three numbers shape every turn: the context window the model is opened with,
the soft response target, and the hard response cap. They used to be one
global setting each (a launcher pref, an env var, a row in ``model_config``),
so switching from a 7B to a 32B kept the 7B's numbers, and the first launcher
default of 8192 followed every model it ever met.

Now the numbers are *resolved* per model::

    explicit env (AI_RPG_CONTEXT_TOKENS, AI_RPG_MAX_RESPONSE_TOKENS, ...)
      > the player's saved custom limits for this model (settings.model_limits)
        > automatic limits from what the model is

Automatic limits come from the GGUF header when there is a file to read
(parameter count, trained context, layers and KV heads for the cache cost) and
the GPU's memory when nvidia-smi answers; otherwise from the parameter count
in the model's name on a tokens-per-billion scale. Nothing here loads the
model: the header is a few kilobytes at the top of the file.

``python -m app.model_limits [--context] [--json] [path-or-config]`` prints the
resolved limits, which is how the PowerShell launcher sizes a managed
llama.cpp server when its context pref is ``auto``.
"""
from __future__ import annotations

import json
import os
import re
import struct
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

SETTINGS_KEY = "model_limits"

# The window a model gets when nothing about it is known.
DEFAULT_CONTEXT_TOKENS = 32768
MIN_CONTEXT_TOKENS = 4096
MAX_CONTEXT_TOKENS = 131072
CONTEXT_STEP = 2048
# The full story contract plus turn headroom needs about this much; auto sizing
# keeps it when the memory allows, and the notice in app/failsafe.py speaks
# when it cannot.
PREFERRED_MIN_CONTEXT = 12288

# Tokens-per-billion scale for the context when only the parameter count is
# known: a 7B gets the full default, a 14B about half, a 70B the floor. The
# KV cache per token grows with the model, so a bigger model on the same
# memory affords fewer tokens; this is the no-GPU stand-in for that fit.
CONTEXT_TOKENS_PER_BILLION = 262144
NO_FACTS_CONTEXT_FLOOR = 8192

# Response caps by parameter count (soft target, hard cap). Small models ramble
# and lose the thread past ~1,200 tokens; larger ones can hold a longer scene.
RESPONSE_CAPS_BY_PARAMS: tuple[tuple[float, int, int], ...] = (
    (4.0, 1200, 1600),
    (10.0, 1500, 2000),
    (20.0, 1800, 2400),
    (float("inf"), 2000, 2600),
)
API_RESPONSE_CAPS = (1500, 2000)
DEFAULT_RESPONSE_CAPS = (1500, 2000)

# Memory the runtime needs beside weights and cache. Playtest #36: a fixed
# 900 MiB sized against 92% of the whole card opened Qwen3 8B at 38,912 tokens
# on a 12 GB card whose desktop already held 1.1 GB, and the first call never
# came back from llama_decode. Now the plan is sized against what is free, the
# compute buffers grow with the window, and a fixed share stays unclaimed for
# the desktop and the driver to move about in.
RUNTIME_OVERHEAD_BYTES = 512 * 1024 * 1024
COMPUTE_BYTES_PER_TOKEN = 32 * 1024
GPU_USABLE_FRACTION = 0.92
# Past this the cache costs memory and prompt time and buys nothing: the turn
# contract needs about 12-16k. Applies to the GPU fit; env and custom win.
AUTO_CONTEXT_CEILING = 24576
KV_BYTES_PER_ELEMENT = 2  # f16 cache, the llama.cpp default

_GGUF_MAGIC = b"GGUF"
_GGUF_SCALAR = {0: "B", 1: "b", 2: "H", 3: "h", 4: "I", 5: "i", 6: "f", 7: "?", 10: "Q", 11: "q", 12: "d"}
_GGUF_STRING = 8
_GGUF_ARRAY = 9
_MAX_HEADER_BYTES = 64 * 1024 * 1024  # a tokenizer vocab array can be large; stop past this

_PARAMS_RE = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)\s*[bB](?![a-zA-Z0-9])")
_SIZE_LABEL_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[bB]")

_gguf_cache: dict[str, tuple[tuple[int, int], dict[str, Any]]] = {}
_gpu_cache: dict[str, Any] = {"at": 0.0, "value": None}
GPU_CACHE_SECONDS = 45.0


# ---------------------------------------------------------------------------
# GGUF header
# ---------------------------------------------------------------------------
def read_gguf_metadata(path: str | Path) -> dict[str, Any]:
    """The key/value header of a GGUF file: architecture, sizes, trained context.

    Reads only the header, never the tensors. Arrays are skipped (their values
    are tokenizer tables) and recorded as their length. Returns {} for a file
    that is missing or not GGUF. Cached by path, size and mtime.
    """
    file_path = Path(str(path or "")).expanduser()
    try:
        stat = file_path.stat()
    except OSError:
        return {}
    key = str(file_path.resolve())
    signature = (int(stat.st_size), int(stat.st_mtime))
    cached = _gguf_cache.get(key)
    if cached and cached[0] == signature:
        return dict(cached[1])
    try:
        meta = _parse_gguf_header(file_path)
    except (OSError, ValueError, struct.error):
        meta = {}
    if meta:
        meta["file_bytes"] = int(stat.st_size)
    _gguf_cache[key] = (signature, meta)
    return dict(meta)


def _parse_gguf_header(file_path: Path) -> dict[str, Any]:
    with file_path.open("rb") as handle:
        if handle.read(4) != _GGUF_MAGIC:
            return {}

        def read(fmt: str) -> Any:
            size = struct.calcsize(fmt)
            raw = handle.read(size)
            if len(raw) != size:
                raise ValueError("truncated GGUF header")
            return struct.unpack("<" + fmt, raw)[0]

        def read_string() -> str:
            length = read("Q")
            if length > _MAX_HEADER_BYTES:
                raise ValueError("GGUF string too long")
            return handle.read(length).decode("utf-8", "replace")

        def skip_value(kind: int) -> Any:
            if kind in _GGUF_SCALAR:
                return read(_GGUF_SCALAR[kind])
            if kind == _GGUF_STRING:
                return read_string()
            if kind == _GGUF_ARRAY:
                element = read("I")
                count = read("Q")
                if count > 50_000_000:
                    raise ValueError("GGUF array too long")
                if element in _GGUF_SCALAR:
                    handle.seek(struct.calcsize(_GGUF_SCALAR[element]) * count, os.SEEK_CUR)
                else:
                    for _ in range(count):
                        skip_value(element)
                return {"__array_len__": count}
            raise ValueError(f"unknown GGUF value type {kind}")

        version = read("I")
        tensor_count = read("Q")
        kv_count = read("Q")
        if kv_count > 10_000:
            raise ValueError("implausible GGUF header")
        meta: dict[str, Any] = {"gguf_version": version, "tensor_count": tensor_count}
        for _ in range(kv_count):
            name = read_string()
            kind = read("I")
            value = skip_value(kind)
            if isinstance(value, dict):
                continue
            if handle.tell() > _MAX_HEADER_BYTES:
                break
            meta[name] = value
        return meta


# ---------------------------------------------------------------------------
# What the model is
# ---------------------------------------------------------------------------
def params_from_text(text: str) -> float | None:
    """A parameter count in billions from a name like qwen3:8b or a size label like 7B."""
    best: float | None = None
    for match in _PARAMS_RE.finditer(str(text or "")):
        value = float(match.group(1))
        if 0.1 <= value <= 2000 and (best is None or value > best):
            best = value
    return best


def model_file_name(name: str) -> str:
    """The model's own name from a path or a repo id: the last part, no .gguf.

    Folders above the file say nothing about the model (playtest #65: a
    session folder with '430b' in it sized an 8B model as 430B).
    """
    last = re.split(r"[\\/]", str(name or "").strip())[-1]
    return re.sub(r"\.gguf$", "", last, flags=re.I)


def model_facts(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Everything auto sizing can learn about the configured model without loading it."""
    cfg = dict(config or {})
    provider = str(cfg.get("provider") or "").strip().lower()
    if provider in {"openai", "openai_compat", "api", "xai", "grok", "spacexai"}:
        name = str(cfg.get("api_model") or cfg.get("model") or "").strip()
        return {"key": f"api:{name.lower()}", "label": name or "API model", "kind": "api", "params_b": params_from_text(name), "name": name}
    path = _gguf_path_for(cfg)
    name = str(cfg.get("mle_model") or cfg.get("model") or "").strip()
    short = model_file_name(name)
    facts: dict[str, Any] = {"kind": "name", "name": name, "params_b": params_from_text(short)}
    if path is not None:
        meta = read_gguf_metadata(path)
        facts["kind"] = "gguf" if meta else "file"
        facts["path"] = str(path)
        facts["key"] = f"gguf:{path.name.lower()}"
        facts["label"] = str(meta.get("general.name") or path.stem)
        facts["file_bytes"] = int(meta.get("file_bytes") or 0) or _file_size(path)
        if meta:
            arch = str(meta.get("general.architecture") or "")
            facts["architecture"] = arch
            label_params = params_from_text(str(meta.get("general.size_label") or ""))
            count = meta.get("general.parameter_count")
            if isinstance(count, (int, float)) and count > 0:
                facts["params_b"] = round(float(count) / 1e9, 2)
            elif label_params is not None:
                facts["params_b"] = label_params
            elif facts.get("params_b") is None:
                facts["params_b"] = params_from_text(path.stem)
            facts["n_ctx_train"] = _int_or_none(meta.get(f"{arch}.context_length"))
            layers = _int_or_none(meta.get(f"{arch}.block_count"))
            embed = _int_or_none(meta.get(f"{arch}.embedding_length"))
            heads = _int_or_none(meta.get(f"{arch}.attention.head_count"))
            kv_heads = _int_or_none(meta.get(f"{arch}.attention.head_count_kv")) or heads
            head_dim = _int_or_none(meta.get(f"{arch}.attention.key_length"))
            if head_dim is None and embed and heads:
                head_dim = embed // heads
            if layers and kv_heads and head_dim:
                facts["kv_bytes_per_token"] = 2 * layers * kv_heads * head_dim * KV_BYTES_PER_ELEMENT
                facts["layers"] = layers
                facts["kv_heads"] = kv_heads
                facts["head_dim"] = head_dim
        elif facts.get("params_b") is None:
            facts["params_b"] = params_from_text(path.stem)
    else:
        facts["key"] = f"mle:{name.lower()}" if name else "mle:unknown"
        facts["label"] = short or "local model"
    return facts


def _gguf_path_for(cfg: dict[str, Any]) -> Path | None:
    raw = str(cfg.get("gguf_model_path") or "").strip()
    if raw:
        candidate = Path(raw).expanduser()
        if candidate.is_file():
            return candidate
    provider = str(cfg.get("provider") or "").strip().lower()
    if provider in {"", "mle", "ollama"}:
        try:
            from app.mle import resolve_model_path

            found = resolve_model_path(str(cfg.get("mle_model") or ""))
        except Exception:
            found = None
        if found is not None:
            return found
    return None


def _file_size(path: Path) -> int:
    try:
        return int(path.stat().st_size)
    except OSError:
        return 0


def _int_or_none(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


# ---------------------------------------------------------------------------
# What the machine has
# ---------------------------------------------------------------------------
def gpu_memory(refresh: bool = False) -> dict[str, int] | None:
    """Total and free memory of the first GPU in bytes, from nvidia-smi; None without one."""
    if os.getenv("AI_RPG_MODEL_LIMITS_NO_GPU", "").strip().lower() in {"1", "true", "yes", "on"}:
        return None
    now = time.monotonic()
    if not refresh and _gpu_cache["value"] is not None and now - float(_gpu_cache["at"]) < GPU_CACHE_SECONDS:
        return dict(_gpu_cache["value"])
    if not refresh and _gpu_cache["value"] is None and _gpu_cache["at"] and now - float(_gpu_cache["at"]) < GPU_CACHE_SECONDS:
        return None
    value = _query_nvidia_smi()
    _gpu_cache["at"] = now
    _gpu_cache["value"] = value
    return dict(value) if value else None


def _query_nvidia_smi() -> dict[str, int] | None:
    try:
        completed = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total,memory.free", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=4,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    for line in completed.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) >= 2:
            try:
                total = int(float(parts[0])) * 1024 * 1024
                free = int(float(parts[1])) * 1024 * 1024
            except ValueError:
                continue
            if total > 0:
                return {"total_bytes": total, "free_bytes": free}
    return None


# ---------------------------------------------------------------------------
# Automatic limits
# ---------------------------------------------------------------------------
def _round_down(value: int, step: int = CONTEXT_STEP) -> int:
    return max(step, (int(value) // step) * step)


def runtime_overhead_bytes(n_ctx: int) -> int:
    """Compute and scratch buffers plus desktop headroom for a window of n_ctx tokens."""
    return RUNTIME_OVERHEAD_BYTES + max(0, int(n_ctx)) * COMPUTE_BYTES_PER_TOKEN


def _gpu_budget_bytes(gpu: dict[str, int]) -> int:
    """What the model may claim: free memory plus what this process already holds, within 92% of the card."""
    total = int(gpu.get("total_bytes") or 0)
    cap = int(total * GPU_USABLE_FRACTION)
    free = gpu.get("free_bytes")
    if free is None:
        return cap
    return min(cap, int(free) + max(0, int(gpu.get("held_bytes") or 0)))


def auto_context_tokens(facts: dict[str, Any], gpu: dict[str, int] | None) -> tuple[int, str]:
    """The context window to open the model with, and one line saying why."""
    trained = _int_or_none(facts.get("n_ctx_train"))
    ceiling = min(trained or DEFAULT_CONTEXT_TOKENS, MAX_CONTEXT_TOKENS)
    params = facts.get("params_b")
    kv_per_token = _int_or_none(facts.get("kv_bytes_per_token"))
    weights = _int_or_none(facts.get("file_bytes"))
    if gpu and kv_per_token and weights:
        budget = _gpu_budget_bytes(gpu)
        usable = budget - weights - RUNTIME_OVERHEAD_BYTES
        card = f"{int(gpu['total_bytes']) / 2**30:.1f} GB GPU ({budget / 2**30:.1f} GB free for the model)"
        if usable <= 0:
            fit = MIN_CONTEXT_TOKENS
            why = f"the {weights / 2**30:.1f} GB of weights leave no room for a cache on this {card}"
        else:
            # Each token costs its cache plus its share of the compute buffers.
            fit = _round_down(usable // (kv_per_token + COMPUTE_BYTES_PER_TOKEN))
            why = (
                f"{fit:,} tokens of cache ({fit * kv_per_token / 2**30:.1f} GB) fit beside "
                f"{weights / 2**30:.1f} GB of weights on a {card}"
            )
        chosen = max(MIN_CONTEXT_TOKENS, min(ceiling, fit, AUTO_CONTEXT_CEILING))
        if chosen == AUTO_CONTEXT_CEILING and fit > AUTO_CONTEXT_CEILING and ceiling > AUTO_CONTEXT_CEILING:
            why = f"capped at {AUTO_CONTEXT_CEILING:,}; more fits ({fit:,}) but a turn needs about 16k"
        elif trained and fit >= trained:
            why = f"trained to {trained:,}; the cache for all of it fits beside {weights / 2**30:.1f} GB of weights"
        return chosen, why
    if params:
        scaled = _round_down(int(CONTEXT_TOKENS_PER_BILLION / float(params)))
        chosen = max(NO_FACTS_CONTEXT_FLOOR, min(ceiling, scaled))
        why = f"{params:g}B parameters on the tokens-per-billion scale" + (f", trained to {trained:,}" if trained else "")
        return chosen, why
    if facts.get("kind") == "api":
        return min(ceiling, DEFAULT_CONTEXT_TOKENS), "the default window; a hosted model sizes its own context"
    return min(ceiling, DEFAULT_CONTEXT_TOKENS), ("trained context" if trained else "the default window; nothing is known about this model")


def auto_response_caps(facts: dict[str, Any]) -> tuple[int, int, str]:
    if facts.get("kind") == "api":
        return API_RESPONSE_CAPS[0], API_RESPONSE_CAPS[1], "API model"
    params = facts.get("params_b")
    if not params:
        return DEFAULT_RESPONSE_CAPS[0], DEFAULT_RESPONSE_CAPS[1], "default caps; parameter count unknown"
    for limit, soft, hard in RESPONSE_CAPS_BY_PARAMS:
        if float(params) < limit:
            return soft, hard, f"{params:g}B parameters"
    soft, hard = RESPONSE_CAPS_BY_PARAMS[-1][1:]
    return soft, hard, f"{params:g}B parameters"


def auto_limits(facts: dict[str, Any], gpu: dict[str, int] | None = None) -> dict[str, Any]:
    context, context_why = auto_context_tokens(facts, gpu)
    soft, hard, caps_why = auto_response_caps(facts)
    return {
        "context_tokens": int(context),
        "response_token_cap": int(soft),
        "response_token_hard_cap": int(hard),
        "basis": {"context": context_why, "response": caps_why},
    }


# ---------------------------------------------------------------------------
# Stored per-model choices
# ---------------------------------------------------------------------------
_store_cache: dict[str, tuple[float, dict[str, Any]]] = {}
STORE_CACHE_SECONDS = 5.0


def _store_key() -> str:
    try:
        from app.db import db_path

        return str(db_path())
    except Exception:
        return ""


def _load_store() -> dict[str, Any]:
    # get_model_config() resolves limits on every call, so the row is read at
    # most once every few seconds per database; a write invalidates it.
    key = _store_key()
    cached = _store_cache.get(key)
    now = time.monotonic()
    if cached and now - cached[0] < STORE_CACHE_SECONDS:
        return dict(cached[1])
    try:
        from app.db import connect

        with connect() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (SETTINGS_KEY,)).fetchone()
    except Exception:
        return {}
    data: dict[str, Any] = {}
    if row:
        try:
            parsed = json.loads(row["value"] or "{}")
        except (TypeError, json.JSONDecodeError):
            parsed = {}
        if isinstance(parsed, dict):
            data = parsed
    _store_cache[key] = (now, dict(data))
    return data


def _save_store(data: dict[str, Any]) -> None:
    from app.db import connect

    with connect() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (SETTINGS_KEY, json.dumps(data, ensure_ascii=True)),
        )
    _store_cache.pop(_store_key(), None)


def stored_limits(model_key: str) -> dict[str, Any] | None:
    entry = _load_store().get(str(model_key or ""))
    return dict(entry) if isinstance(entry, dict) else None


def set_limits(model_key: str, values: dict[str, Any] | None) -> dict[str, Any] | None:
    """Remember the player's numbers for one model, or forget them (back to auto)."""
    key = str(model_key or "").strip()
    if not key:
        return None
    store = _load_store()
    if not values:
        store.pop(key, None)
        _save_store(store)
        return None
    entry: dict[str, Any] = {"mode": "custom", "saved_at": time.time()}
    for name, floor, ceiling in (
        ("context_tokens", MIN_CONTEXT_TOKENS, MAX_CONTEXT_TOKENS),
        ("response_token_cap", 64, 100_000),
        ("response_token_hard_cap", 64, 100_000),
    ):
        raw = values.get(name)
        if raw in (None, "", "auto"):
            continue
        try:
            entry[name] = max(floor, min(ceiling, int(raw)))
        except (TypeError, ValueError):
            continue
    if "response_token_cap" in entry and "response_token_hard_cap" in entry:
        entry["response_token_hard_cap"] = max(entry["response_token_cap"], entry["response_token_hard_cap"])
    store[key] = entry
    _save_store(store)
    return entry


def forget_limits(model_key: str) -> None:
    set_limits(model_key, None)


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------
def _env_positive_int(*names: str) -> int | None:
    for name in names:
        raw = str(os.getenv(name) or "").strip()
        if not raw or raw.lower() == "auto":
            continue
        try:
            value = int(raw)
        except ValueError:
            continue
        if value > 0:
            return value
    return None


def resolve_limits(config: dict[str, Any] | None = None, *, with_facts: bool = True) -> dict[str, Any]:
    """The three limits for the configured model, with where each came from.

    Precedence per limit: explicit env > the player's custom value for this
    model > automatic. ``source`` names which one won for each limit.
    """
    cfg = dict(config or {})
    if not cfg:
        try:
            from app.llm import get_model_config

            cfg = get_model_config(ignore_override=True, resolve_limits=False)
        except Exception:
            cfg = {}
    facts = model_facts(cfg)
    gpu = gpu_memory() if facts.get("kind") in {"gguf", "file", "name"} else None
    if gpu:
        held = _held_by_loaded_model(facts)
        if held:
            gpu = {**gpu, "held_bytes": held}
    auto = auto_limits(facts, gpu)
    custom = stored_limits(str(facts.get("key") or "")) or {}
    env_values = {
        "context_tokens": _env_positive_int("AI_RPG_LLAMA_CPP_CONTEXT", "AI_RPG_CONTEXT_TOKENS")
        if str(cfg.get("provider") or "").lower() == "llama_cpp"
        else _env_positive_int("AI_RPG_CONTEXT_TOKENS"),
        "response_token_cap": _env_positive_int("AI_RPG_MAX_RESPONSE_TOKENS"),
        "response_token_hard_cap": _env_positive_int("AI_RPG_RESPONSE_HARD_CAP_TOKENS", "AI_RPG_MAX_RESPONSE_HARD_CAP_TOKENS"),
    }
    resolved: dict[str, Any] = {}
    source: dict[str, str] = {}
    for name in ("context_tokens", "response_token_cap", "response_token_hard_cap"):
        if env_values.get(name):
            resolved[name] = int(env_values[name])
            source[name] = "env"
        elif custom.get(name):
            resolved[name] = int(custom[name])
            source[name] = "custom"
        else:
            resolved[name] = int(auto[name])
            source[name] = "auto"
    resolved["response_token_hard_cap"] = max(resolved["response_token_cap"], resolved["response_token_hard_cap"])
    mode = "custom" if custom else "auto"
    out: dict[str, Any] = {
        "model_key": facts.get("key") or "",
        "label": facts.get("label") or facts.get("name") or "",
        "mode": mode,
        "context_tokens": resolved["context_tokens"],
        "response_token_cap": resolved["response_token_cap"],
        "response_token_hard_cap": resolved["response_token_hard_cap"],
        "source": source,
        "auto": auto,
        "custom": custom or None,
    }
    if with_facts:
        out["facts"] = {
            key: facts.get(key)
            for key in ("kind", "name", "path", "params_b", "n_ctx_train", "kv_bytes_per_token", "file_bytes", "architecture")
            if facts.get(key) is not None
        }
        out["gpu"] = gpu
    return out


def _held_by_loaded_model(facts: dict[str, Any]) -> int:
    """VRAM our own in-process model already holds, so re-resolving while it is loaded does not shrink the window."""
    mle = sys.modules.get("app.mle")
    if mle is None or getattr(mle, "_MODEL", None) is None:
        return 0
    path = str(getattr(mle, "_MODEL_PATH", "") or "")
    n_ctx = int(getattr(mle, "_MODEL_CTX", 0) or 0)
    if not path:
        return 0
    weights = _file_size(Path(path))
    kv = _int_or_none(facts.get("kv_bytes_per_token")) or 0
    same = str(facts.get("path") or "") and Path(str(facts.get("path"))).resolve() == Path(path).resolve()
    cache = n_ctx * kv if same else 0
    return weights + cache + (runtime_overhead_bytes(n_ctx) - RUNTIME_OVERHEAD_BYTES)


def describe(resolved: dict[str, Any]) -> str:
    """One line for a menu or a log: the numbers and why."""
    auto = resolved.get("auto") or {}
    basis = auto.get("basis") or {}
    mode = resolved.get("mode") or "auto"
    head = (
        f"{resolved.get('label') or 'model'}: context {int(resolved.get('context_tokens') or 0):,}, "
        f"response {int(resolved.get('response_token_cap') or 0):,} / {int(resolved.get('response_token_hard_cap') or 0):,}"
    )
    if mode == "custom":
        return head + " (your saved limits for this model)"
    return head + f" (auto: {basis.get('context') or 'default'})"


# ---------------------------------------------------------------------------
# Command line (used by the PowerShell launcher)
# ---------------------------------------------------------------------------
def _main(argv: list[str]) -> int:
    want_json = "--json" in argv
    want_context = "--context" in argv
    positional = [arg for arg in argv if not arg.startswith("--")]
    cfg: dict[str, Any] = {}
    if positional:
        cfg = {"provider": "llama_cpp", "gguf_model_path": positional[0]}
    resolved = resolve_limits(cfg or None)
    if want_context:
        print(int(resolved["context_tokens"]))
    elif want_json:
        print(json.dumps(resolved, indent=2, default=str))
    else:
        print(describe(resolved))
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
