"""Failsafes: turn a raw engine error into a problem the player can act on.

An LLM failure used to arrive in the browser as one line of exception text,
and the game either stopped on it or quietly wrote a deterministic turn in its
place. Neither told the player what went wrong or what to do. This module is
the one place that knows both:

  * ``classify_failure(text)`` maps an error message to a ``problem``: a code,
    a title, a one-line summary, plain-language tips, and (per stage) the
    fallback the player may accept with "Continue anyway".
  * ``FailsafeBlocked`` is raised by a turn that hit a model error while the
    caller asked not to fall back silently. The API turns it into a 503 whose
    detail carries the problem; the browser shows the dialog and may resend
    the turn with ``allow_fallback`` set.
  * ``context_problem`` is the MLE loader's specific case: the requested
    context did not fit, and the smaller one is on offer.

Problems are plain dicts so they serialise as-is. Tips are written for the
player, not the developer: what to close, what to lower, where the setting is.
"""
from __future__ import annotations

import re
from typing import Any

MLE_FALLBACK_ENDPOINT = "/api/failsafe/mle-fallback"

OFFLINE_NARRATOR = {
    "kind": "turn_fallback",
    "label": "Continue anyway",
    "note": (
        "This turn will be written by the offline narrator: short, deterministic prose with no model. "
        "The world still moves. You can Rewrite the turn once the model is back."
    ),
}

RETRY_ACTION = {"id": "retry", "label": "Retry"}
SETTINGS_ACTION = {"id": "settings", "label": "Open LLM settings"}


class FailsafeBlocked(RuntimeError):
    """A model failure the caller wants surfaced instead of papered over."""

    def __init__(self, problem: dict[str, Any]):
        super().__init__(str(problem.get("summary") or problem.get("title") or "Model failure"))
        self.problem = problem


# Order matters: the first rule whose marker appears in the lowered text wins,
# so the specific ones (memory, missing file) come before the broad ones.
_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("out_of_memory", (
        "out of memory", "failed to allocate", "cudamalloc", "bad_alloc", "memoryerror",
        "not enough memory", "insufficient memory", "unable to allocate", "cuda error",
        "kv cache", "kv_cache", "did not load)", "n_ctx",
    )),
    ("engine_missing", ("could not import llama_cpp", "no module named")),
    ("model_missing", (
        "no model loaded", "set mle_model", "no such file", "does not exist", "missing model",
        "model file", "not found",
    )),
    ("server_unreachable", (
        "connection refused", "econnrefused", "winerror 10061", "failed to establish",
        "max retries", "name or service not known", "getaddrinfo", "connect call failed",
        "remote end closed", "connection reset", "unreachable", "could not start managed",
        "server did not", "not answering",
    )),
    ("auth", ("unauthorized", "invalid api key", "incorrect api key", "forbidden", "authentication")),
    ("rate_limit", ("rate limit", "too many requests", "quota exceeded", "429")),
    ("timeout", ("timed out", "timeout", "deadline exceeded")),
    ("bad_output", (
        "json", "malformed", "non-object", "could not parse", "readable narration",
        "echoed the setup schema", "no usable", "empty completion", "empty response",
    )),
)

_HTTP_AUTH_RE = re.compile(r"\b(401|403)\b")

_COPY: dict[str, dict[str, Any]] = {
    "out_of_memory": {
        "title": "The model did not fit in memory",
        "summary": "Loading or running the model ran out of RAM or video memory.",
        "tips": [
            "Close apps using a lot of RAM or video memory: browsers with many tabs, games, image tools, other model servers.",
            "Lower Context tokens in the Gatehouse menu (or AI_RPG_CONTEXT_TOKENS). 8192 is enough for most scenes.",
            "Pick a smaller quantization of the same model, for example Q4 instead of Q8, or a smaller model.",
            "If the model runs on the GPU, set fewer GPU layers so part of it stays in system RAM.",
        ],
    },
    "engine_missing": {
        "title": "The local engine is not installed",
        "summary": "Python could not import llama_cpp, so no GGUF can run in-process.",
        "tips": [
            "Run the launcher once with the install step, or run: pip install llama-cpp-python inside .venv.",
            "Or switch Provider in LLM settings to a llama.cpp server or a cloud API.",
        ],
    },
    "model_missing": {
        "title": "No model file at that path",
        "summary": "The engine is set to a GGUF it cannot find.",
        "tips": [
            "Open LLM settings and point Model Path at an existing .gguf file.",
            "Or drop the file into data/mle-models/ and set MLE model to its name.",
            "Check the spelling and the drive letter; a moved download is the usual cause.",
        ],
    },
    "server_unreachable": {
        "title": "The LLM server is not answering",
        "summary": "Nothing is listening at the configured address, or a firewall is in the way.",
        "tips": [
            "Start the llama.cpp server (or the API gateway) and press Test Connection in LLM settings.",
            "Check the Server URL and port; the default local server is http://localhost:8080.",
            "If it started a moment ago, give it time to load the model, then retry.",
            "On a second machine, allow the port through the firewall and bind the server to 0.0.0.0.",
        ],
    },
    "auth": {
        "title": "The API rejected the key",
        "summary": "The cloud provider answered that the key is missing, wrong, or not allowed for this model.",
        "tips": [
            "Paste the key again in LLM settings; keys are easy to truncate when copied.",
            "Make sure the key belongs to the provider selected under API preset.",
            "Check the account has access to the chosen model and has credit.",
        ],
    },
    "rate_limit": {
        "title": "The API is rate-limiting requests",
        "summary": "Too many requests, or the account's quota is used up.",
        "tips": [
            "Wait a minute and retry.",
            "Lower the Soft and Hard token caps so each turn asks for less.",
            "Check the provider dashboard for quota or billing limits.",
        ],
    },
    "timeout": {
        "title": "The model took too long",
        "summary": "No answer arrived before the time limit.",
        "tips": [
            "Lower the Soft and Hard token caps in LLM settings so turns are shorter.",
            "Close other heavy apps; a model sharing the GPU or CPU slows down a lot.",
            "A smaller model or a smaller quantization answers faster on this hardware.",
        ],
    },
    "bad_output": {
        "title": "The model answered, but not in a usable shape",
        "summary": "The reply could not be read as a scene.",
        "tips": [
            "Retry once; small models occasionally drop the format.",
            "Raise the Hard token cap a little so the reply is not cut off mid-sentence.",
            "If it keeps happening with one model, try a different quantization or model.",
        ],
    },
    "unknown": {
        "title": "The model call failed",
        "summary": "Something went wrong while generating.",
        "tips": [
            "Retry once.",
            "Press Test Connection in LLM settings to see whether the engine is reachable.",
            "Check the terminal window that runs Mørkyn for the full error.",
        ],
    },
}


def classify_failure(message: Any, *, stage: str = "turn", provider: str = "") -> dict[str, Any]:
    """Map an error message to a problem the UI can show.

    ``stage`` is "turn" (a scene was being written: the offline narrator is on
    offer), "load" (the model was being opened or probed: no turn fallback),
    or "runtime" (a background status).
    """
    raw = str(message or "").strip()
    low = raw.lower()
    code = "unknown"
    for candidate, markers in _RULES:
        if any(m in low for m in markers):
            code = candidate
            break
    if code == "unknown" and _HTTP_AUTH_RE.search(raw):
        code = "auth"
    copy = _COPY.get(code) or _COPY["unknown"]
    tips = list(copy["tips"])
    if provider == "mle" and code == "server_unreachable":
        # The in-process engine has no server; the message came from somewhere else.
        tips = _COPY["unknown"]["tips"]
    problem: dict[str, Any] = {
        "code": code,
        "stage": stage,
        "provider": provider or "",
        "title": copy["title"],
        "summary": copy["summary"],
        "tips": tips,
        "detail": raw[:600],
        "actions": [RETRY_ACTION, SETTINGS_ACTION],
        "fallback": dict(OFFLINE_NARRATOR) if stage == "turn" else None,
    }
    return problem


def context_problem(requested: int, fallback: int, error: str = "") -> dict[str, Any]:
    """The MLE loader's case: the requested context did not fit; a smaller one is on offer."""
    return {
        "code": "context_too_large",
        "stage": "load",
        "provider": "mle",
        "title": "The model did not fit at the requested context size",
        "summary": (
            f"Loading with a {requested:,}-token context failed. {fallback:,} tokens is still enough for most "
            "scenes, but long sessions will remember less of what came before."
        ),
        "tips": [
            "Close apps using a lot of RAM or video memory, then Retry at the full size.",
            "Lower Context tokens in the Gatehouse menu so the smaller size is the normal one.",
            "A smaller quantization of the same model (Q4 instead of Q8) frees room for context.",
            "If the model runs on the GPU, set fewer GPU layers so the context cache fits.",
        ],
        "detail": str(error or "")[:600],
        "actions": [RETRY_ACTION, SETTINGS_ACTION],
        "fallback": {
            "kind": "endpoint",
            "url": MLE_FALLBACK_ENDPOINT,
            "label": f"Continue with {fallback:,} tokens",
            "note": (
                f"The {fallback:,}-token context stays until Mørkyn restarts. To make it permanent, set Context "
                "tokens in the Gatehouse, or AI_RPG_CONTEXT_FALLBACK=auto to always accept it."
            ),
        },
    }


def context_notice(window: int, needed: int, provider: str = "mle") -> dict[str, Any]:
    """The configured context is smaller than the full story contract.

    Not a failure: the compact contract runs and the game plays. It is still
    worth a dialog, because the only other sign was one line on the server
    console, and a launcher once seeded prefs with 8,192 by default.
    """
    return {
        "code": "context_below_contract",
        "stage": "runtime",
        "provider": provider,
        "title": "The context is smaller than the full story contract",
        "summary": (
            f"The model runs with a {window:,}-token context. The full narrator contract needs about "
            f"{needed:,}, so Mørkyn is using the compact one: scenes still play, but each turn keeps less "
            "of the world in view."
        ),
        "tips": [
            "Raise Context tokens in the Gatehouse menu (option C) to 32768, or set AI_RPG_CONTEXT_TOKENS, then restart Mørkyn.",
            "If the larger context does not fit in memory, a smaller quantization of the same model (Q4 instead of Q8) frees room for it.",
            "If you chose the smaller size on purpose, nothing is wrong; this notice shows once for each context size.",
        ],
        "detail": f"context_window={window} needed={needed}",
        "actions": [SETTINGS_ACTION],
        "fallback": None,
    }


def stale_server_notice(changed: list[str]) -> dict[str, Any]:
    """The Python on disk changed after this server started.

    The page script is read fresh from disk on every load, but the server keeps
    the Python it started with. The two drift apart after an update: one save
    was set up by a new page against an old server, which ignored the new gear
    list and kept the page's placeholder names ("boots, tunic, trousers").
    """
    shown = ", ".join(changed[:4]) + (" and more" if len(changed) > 4 else "")
    return {
        "code": "stale_server",
        "stage": "runtime",
        "provider": "",
        "title": "Mørkyn was updated while it was running",
        "summary": (
            "The game's files changed after this server started, so the page and the server are now "
            "different versions. New games and turns can come out wrong until you restart."
        ),
        "tips": [
            "Close the Mørkyn server window and start it again from the launcher.",
            "Your saves are safe; restarting does not touch them.",
        ],
        "detail": f"changed since start: {shown}",
        "actions": [],
        "fallback": None,
    }


def problem_detail(problem: dict[str, Any]) -> dict[str, Any]:
    """The HTTP error body: a message for old clients plus the problem for new ones."""
    return {"message": str(problem.get("summary") or problem.get("title") or "Model failure"), "problem": problem}
