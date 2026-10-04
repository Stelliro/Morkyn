"""Morkyn LLM Engine (MLE).

Loads one local GGUF in-process and returns that completion only.
A listed word can be hidden for one call by masking whole-word tokens
at sample time. The weights file is not rewritten, and the returned
text is not edited.
"""

from __future__ import annotations

import os
import re
import threading
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from app.narration_pipeline import _STRUCTURE_WORDS

ENGINE_NAME = "MLE"
DEFAULT_MODEL = "qwen3:8b"
_FALLBACK_CONTEXT = 8192
_SPACE_MARKERS = ("\u2581", "\u0120")
_FORBIDDEN_CHARS = set("@[]{}<>")
_WORD_RE = re.compile(r"^[a-z][a-z'-]*$")
_CODE_RE = re.compile(r"^[a-z]+\d+[a-z0-9]*$")
_DIGIT_RE = re.compile(r"^\d+$")

_LOCK = threading.Lock()
# How long status() waits for _LOCK when the model still has to load. A turn
# in flight holds the lock for up to the MLE timeout; status must not.
_STATUS_LOCK_WAIT = 2.0
_MODEL = None
_MODEL_PATH = ""
_MODEL_CTX = 0
_DETAIL = ""
_KEY_CACHE: dict[str, tuple[str, ...]] = {}
_BAN_CACHE: dict[tuple[str, tuple[str, ...]], tuple[int, ...]] = {}
# The smaller context is used only once someone said yes to it (or the
# policy is auto). Per process: a restart asks again, on purpose.
_FALLBACK_ALLOWED = False
_LAST_PROBLEM: dict[str, Any] | None = None


class MleNotReady(RuntimeError):
    """MLE is the engine in use, and no model is loaded in it yet."""

    def __init__(self, message: str = "", problem: dict[str, Any] | None = None):
        super().__init__(message)
        self.problem = problem


def models_dir() -> Path:
    """Directory of local GGUF weights. data/ is gitignored."""
    return Path(__file__).resolve().parent.parent / "data" / "mle-models"


def piece_should_hide(
    piece: str,
    hide_words: Iterable[str] | None,
    keep_words: Iterable[str] | None = None,
) -> bool:
    """True when this decoded token piece is exactly one hidden word.

    A piece the tokenizer split off a longer word stays visible. Length-1
    pieces, digits, letter-digit codes, punctuation, structure words, keep
    words, and pieces containing @ or brackets are never hidden.
    """
    key = _maskable_key(piece)
    if not key:
        return False
    if key in _word_set(keep_words):
        return False
    return key in _word_set(hide_words)


def resolve_model_path(model: str = "") -> Path | None:
    """Find a GGUF: explicit path, named file, MLE_GGUF, else the only file."""
    requested = str(model or "").strip()
    env_model = str(os.getenv("MLE_MODEL") or "").strip()
    for candidate in (requested, env_model):
        found = _file_if_exists(candidate)
        if found is not None:
            return found
    for candidate in (requested, env_model):
        found = _named_model_file(candidate)
        if found is not None:
            return found
    found = _file_if_exists(os.getenv("MLE_GGUF") or "")
    if found is not None:
        return found
    files = _gguf_files(models_dir())
    if len(files) == 1:
        return files[0]
    return None


def chat(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str = "",
    timeout: int = 90,
    temperature: float = 0.75,
    max_tokens: int | None = None,
    response_format: str | None = None,
    hide_words: Iterable[str] | None = None,
    keep_words: Iterable[str] | None = None,
) -> str:
    """Return the new completion text only. Raises when no GGUF is loaded."""
    path = resolve_model_path(model)
    if path is None:
        raise MleNotReady(missing_model_detail(model))
    with _LOCK:
        _ensure_loaded(path)
        assert _MODEL is not None
        return _generate(
            _MODEL,
            str(path.resolve()),
            system_prompt,
            user_prompt,
            timeout=timeout,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
            hide_words=hide_words,
            keep_words=keep_words,
        )


def loaded_context() -> int:
    """The context the in-process model actually loaded with, or 0 when none is loaded.

    Read without the lock: a stale answer during a reload is harmless, and the
    budget code asks on every call.
    """
    return int(_MODEL_CTX or 0) if _MODEL is not None else 0


def status(model: str = "") -> dict[str, Any]:
    """ok is true only after the GGUF file has loaded."""
    label = _label(model)
    path = resolve_model_path(model)
    if path is None:
        return {
            "ok": False,
            "engine": ENGINE_NAME,
            "model": label,
            "detail": missing_model_detail(model),
        }
    # Already loaded for this path: _ensure_loaded would be a no-op, and
    # waiting on _LOCK here parks Test Connection (and the context-fallback
    # endpoint) behind a turn in flight for the rest of that turn.
    report = _loaded_report(label, str(path.resolve()))
    if report is not None:
        return report
    if not _LOCK.acquire(timeout=_STATUS_LOCK_WAIT):
        return {
            "ok": False,
            "busy": True,
            "engine": ENGINE_NAME,
            "model": label,
            "detail": f"{ENGINE_NAME} is generating a turn; try again when it finishes.",
        }
    try:
        _ensure_loaded(path)
        detail = _DETAIL
        loaded = _MODEL is not None
        context = _MODEL_CTX
    except MleNotReady as exc:
        report = {
            "ok": False,
            "engine": ENGINE_NAME,
            "model": label,
            "detail": str(exc),
        }
        if getattr(exc, "problem", None):
            report["problem"] = exc.problem
        return report
    finally:
        _LOCK.release()
    return {
        "ok": loaded,
        "engine": ENGINE_NAME,
        "model": label,
        "detail": detail if loaded else missing_model_detail(model),
        "context": context if loaded else 0,
        "context_requested": _context_tokens(),
    }


def _loaded_report(label: str, resolved: str) -> dict[str, Any] | None:
    """The status report when the model for ``resolved`` is already in memory, else None.

    Read without the lock, like loaded_context(): the fields are snapshotted
    once, and a reload racing this read only costs a stale answer.
    """
    model, loaded_path, context, detail = _MODEL, _MODEL_PATH, _MODEL_CTX, _DETAIL
    if model is None or loaded_path != resolved:
        return None
    return {
        "ok": True,
        "engine": ENGINE_NAME,
        "model": label,
        "detail": detail,
        "context": context,
        "context_requested": _context_tokens(),
    }


def missing_model_detail(model: str = "") -> str:
    label = _label(model)
    directory = models_dir()
    requested = str(model or "").strip() or str(os.getenv("MLE_MODEL") or "").strip()
    where = str(directory)
    if requested and _looks_like_path(requested):
        where = requested
    else:
        bare = _bare_filename(requested)
        if bare:
            filename = bare if bare.lower().endswith(".gguf") else f"{bare}.gguf"
            where = str(directory / filename)
    return (
        f"MLE has no model loaded ({label}). "
        f"Set mle_model or MLE_MODEL to a GGUF file path ({where})."
    )


def _label(model: str) -> str:
    chosen = str(model or "").strip() or str(os.getenv("MLE_MODEL") or "").strip()
    return chosen or DEFAULT_MODEL


def _context_tokens() -> int:
    """The window to open the model with: explicit env, else the model's resolved limit."""
    raw = os.getenv("AI_RPG_CONTEXT_TOKENS", "").strip()
    try:
        value = int(raw)
    except ValueError:
        value = 0
    if value > 0:
        return value
    try:
        from app.model_limits import resolve_limits

        resolved = int(resolve_limits(with_facts=False)["context_tokens"])
    except Exception:
        resolved = 0
    return resolved if resolved > 0 else 32768


def _gpu_layers() -> int:
    raw = os.getenv("AI_RPG_LLAMA_CPP_GPU_LAYERS", "-1").strip()
    try:
        return int(raw)
    except ValueError:
        return -1


def _flash_attn() -> bool:
    raw = os.getenv("AI_RPG_LLAMA_CPP_FLASH_ATTN", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _fallback_policy() -> str:
    """ask: stop at the requested size and offer the smaller one. auto: shrink silently."""
    return str(os.getenv("AI_RPG_CONTEXT_FALLBACK", "ask") or "ask").strip().lower()


def allow_context_fallback(flag: bool = True) -> None:
    """The player (or a script) accepted the smaller context for this process."""
    global _FALLBACK_ALLOWED
    _FALLBACK_ALLOWED = bool(flag)


def fallback_allowed() -> bool:
    return _FALLBACK_ALLOWED or _fallback_policy() == "auto"


def last_problem() -> dict[str, Any] | None:
    """The problem from the last failed load, for /api/model-status; None once a load succeeds."""
    return dict(_LAST_PROBLEM) if _LAST_PROBLEM else None


def _maskable_key(piece: str) -> str:
    raw = str(piece or "")
    if any(ch in raw for ch in _FORBIDDEN_CHARS):
        return ""
    text = raw
    for mark in _SPACE_MARKERS:
        text = text.replace(mark, " ")
    word = text.strip().lower()
    if len(word) < 2 or _DIGIT_RE.fullmatch(word) or _CODE_RE.fullmatch(word):
        return ""
    if not _WORD_RE.fullmatch(word) or word in _STRUCTURE_WORDS:
        return ""
    return word


def _word_set(words: Iterable[str] | None) -> set[str]:
    out: set[str] = set()
    for word in words or ():
        text = str(word or "").strip().lower()
        if text:
            out.add(text)
    return out


def _looks_like_path(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if text.lower().endswith(".gguf") or "/" in text or "\\" in text:
        return True
    return len(text) > 2 and text[1] == ":"


def _bare_filename(value: str) -> str:
    text = str(value or "").strip()
    if not text or text in {".", ".."}:
        return ""
    if any(ch in text for ch in '\\/:*?"<>|'):
        return ""
    return text


def _file_if_exists(value: str) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    path = Path(text).expanduser()
    try:
        if path.is_file():
            return path
    except OSError:
        return None
    return None


def _named_model_file(name: str) -> Path | None:
    bare = _bare_filename(name)
    if not bare:
        return None
    filename = bare if bare.lower().endswith(".gguf") else f"{bare}.gguf"
    return _file_if_exists(str(models_dir() / filename))


def _gguf_files(directory: Path) -> list[Path]:
    try:
        if not directory.is_dir():
            return []
        found = [
            path
            for path in directory.iterdir()
            if path.is_file() and path.suffix.lower() == ".gguf"
        ]
    except OSError:
        return []
    return sorted(found)


def _close_quiet(model) -> None:
    try:
        model.close()
    except Exception:
        pass


def _drop_model() -> None:
    global _MODEL, _MODEL_PATH, _MODEL_CTX
    if _MODEL is not None:
        _close_quiet(_MODEL)
    _MODEL = None
    _MODEL_PATH = ""
    _MODEL_CTX = 0
    _KEY_CACHE.clear()
    _BAN_CACHE.clear()


def _open_model(path: str, n_ctx: int):
    try:
        from llama_cpp.llama import Llama
    except Exception as exc:
        raise MleNotReady(f"MLE could not import llama_cpp to load {path}. {exc}") from exc
    return Llama(
        model_path=path,
        n_ctx=n_ctx,
        n_batch=min(512, n_ctx),
        n_gpu_layers=_gpu_layers(),
        flash_attn=_flash_attn(),
        use_mmap=True,
        use_mlock=False,
        verbose=False,
    )


def _ensure_loaded(path: Path) -> None:
    global _MODEL, _MODEL_PATH, _MODEL_CTX, _DETAIL, _LAST_PROBLEM
    resolved = str(path.resolve())
    requested = _context_tokens()
    if _MODEL is not None and _MODEL_PATH == resolved:
        # Same file, same window: nothing to do. Same file at the accepted
        # fallback size with a bigger request: that fallback stands. Any
        # other change in the requested window (the player edited the
        # model's limits) reopens the file at the new size.
        if _MODEL_CTX == requested or (_MODEL_CTX == _FALLBACK_CONTEXT and requested > _FALLBACK_CONTEXT):
            return
    _drop_model()
    # A smaller context is a fallback only when the request is bigger than it,
    # and it is tried only once someone has accepted it: the browser shows the
    # tips and a "continue anyway" button, and AI_RPG_CONTEXT_FALLBACK=auto
    # says yes in advance for scripts and headless runs.
    can_shrink = requested > _FALLBACK_CONTEXT
    attempts = [requested] + ([_FALLBACK_CONTEXT] if can_shrink and fallback_allowed() else [])
    errors: list[str] = []
    for n_ctx in attempts:
        loaded = None
        try:
            loaded = _open_model(resolved, n_ctx)
        except Exception as exc:
            errors.append(f"context {n_ctx}: {exc}")
            if loaded is not None:
                _close_quiet(loaded)
            continue
        _MODEL = loaded
        _MODEL_PATH = resolved
        _MODEL_CTX = n_ctx
        _LAST_PROBLEM = None
        if n_ctx == requested:
            _DETAIL = f"Loaded {resolved} in-process (context {n_ctx})."
        else:
            _DETAIL = (
                f"Loaded {resolved} in-process (context {n_ctx}; "
                f"{requested} did not load)."
            )
        return
    if can_shrink and not fallback_allowed():
        from app.failsafe import context_problem

        _LAST_PROBLEM = context_problem(requested, _FALLBACK_CONTEXT, errors[-1] if errors else "")
        raise MleNotReady(
            f"MLE could not load {resolved} at context {requested}. " + " ".join(errors)
            + f" Accept the {_FALLBACK_CONTEXT}-token fallback to continue.",
            problem=_LAST_PROBLEM,
        )
    raise MleNotReady(f"MLE could not load {resolved}. " + " ".join(errors))


def _vocab_keys(model, path: str) -> tuple[str, ...]:
    cached = _KEY_CACHE.get(path)
    if cached is not None:
        return cached
    import ctypes

    from llama_cpp import llama_cpp

    vocab = model._model.vocab
    n_vocab = int(model.n_vocab())
    size = 32
    buf = ctypes.create_string_buffer(size)
    keys: list[str] = []
    for token in range(n_vocab):
        n_chars = int(llama_cpp.llama_token_to_piece(vocab, token, buf, size, 0, True))
        if n_chars < 0:
            need = -n_chars
            size = max(size * 2, need + 8, 64)
            if size > 8192:
                keys.append("")
                continue
            buf = ctypes.create_string_buffer(size)
            n_chars = int(llama_cpp.llama_token_to_piece(vocab, token, buf, size, 0, True))
        if n_chars <= 0:
            keys.append("")
            continue
        piece = buf.raw[:n_chars].decode("utf-8", errors="replace")
        keys.append(_maskable_key(piece))
    stored = tuple(keys)
    _KEY_CACHE[path] = stored
    return stored


def _banned_ids(model, path: str, hide_words, keep_words) -> tuple[int, ...]:
    keep = _word_set(keep_words)
    hide = {key for key in (_maskable_key(word) for word in (hide_words or ())) if key and key not in keep}
    if not hide:
        return ()
    cache_key = (path, tuple(sorted(hide)))
    cached = _BAN_CACHE.get(cache_key)
    if cached is not None:
        return cached
    keys = _vocab_keys(model, path)
    banned = tuple(index for index, key in enumerate(keys) if key in hide)
    _BAN_CACHE[cache_key] = banned
    return banned


class _SampleMask:
    """Sample-time logit mask for one generation. Does not edit the text."""

    def __init__(self, banned, deadline: float, eos_id: int) -> None:
        self.banned = banned
        self.deadline = deadline
        self.eos_id = eos_id
        # Set once the deadline forces EOS. Without it the truncated text came
        # back as a normal completion and no timeout guard could see it.
        self.hit = False

    def __call__(self, input_ids, scores):
        del input_ids
        import numpy as np

        if self.deadline and time.monotonic() >= self.deadline:
            self.hit = True
            stopped = np.array(scores, dtype=np.float32, copy=True)
            stopped[:] = -np.inf
            if 0 <= self.eos_id < stopped.shape[0]:
                stopped[self.eos_id] = np.float32(0)
            return stopped
        banned = self.banned
        if banned is None or getattr(banned, "size", 0) == 0:
            return scores
        n = int(scores.shape[0])
        valid = banned[banned < n]
        if valid.size == 0:
            return scores
        try:
            scores[valid] = -np.inf
            return scores
        except Exception:
            updated = np.array(scores, dtype=np.float32, copy=True)
            updated[valid] = -np.inf
            return updated


def _generate(
    model,
    path: str,
    system_prompt: str,
    user_prompt: str,
    *,
    timeout: int,
    temperature: float,
    max_tokens: int | None,
    response_format: str | None,
    hide_words,
    keep_words,
) -> str:
    import numpy as np
    from llama_cpp.llama import LogitsProcessorList

    banned_tokens = _banned_ids(model, path, hide_words, keep_words)
    banned = np.asarray(banned_tokens, dtype=np.int32)
    deadline = time.monotonic() + max(0, int(timeout)) if int(timeout or 0) > 0 else 0.0
    processor = None
    mask = None
    if banned.size or deadline:
        try:
            eos_id = int(model.token_eos())
        except Exception:
            eos_id = -1
        mask = _SampleMask(banned, deadline, eos_id)
        processor = LogitsProcessorList([mask])
    token_limit = None if max_tokens is None else int(max_tokens)
    if token_limit is not None and token_limit <= 0:
        token_limit = None
    fmt = str(response_format or "").strip().lower()
    try:
        payload = model.create_chat_completion(
            messages=[
                {"role": "system", "content": system_prompt or ""},
                {"role": "user", "content": user_prompt or ""},
            ],
            temperature=float(temperature),
            max_tokens=token_limit,
            response_format={"type": "json_object"} if fmt == "json" else None,
            logits_processor=processor,
            stream=False,
        )
    except MleNotReady:
        raise
    except Exception as exc:
        raise MleNotReady(f"MLE generation failed ({path}). {exc}") from exc
    text = _completion_text(payload)
    if mask is not None and mask.hit:
        # The deadline forced EOS mid-generation. Raise the same way a server
        # timeout does so the timeout guards (and the failsafe) see it instead
        # of parsing a truncated draft as a finished turn.
        raise MleNotReady(
            f"MLE generation timed out after {int(timeout)}s ({path}); "
            f"{len(text)} characters were produced before the deadline."
        )
    return text


def _completion_text(payload) -> str:
    if isinstance(payload, str):
        return payload
    if not isinstance(payload, dict):
        return "" if payload is None else str(payload)
    choices = payload.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        return ""
    choice = choices[0]
    message = choice.get("message")
    content = message.get("content") if isinstance(message, dict) else choice.get("text")
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                text = part.get("text")
                if text is None:
                    text = part.get("content")
                parts.append("" if text is None else str(text))
        return "".join(parts)
    return str(content)
