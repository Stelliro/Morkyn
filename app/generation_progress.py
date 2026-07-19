"""
Thread-safe generation progress for the web UI.

The draft/verify/narration pipeline runs on the request thread; the browser polls
GET /api/generation-progress to show phase lines and accepted paragraph previews
while "Local model is working".
"""
from __future__ import annotations

import threading
import time
from typing import Any


_lock = threading.Lock()
_state: dict[str, Any] = {
    "active": False,
    "job": "",
    "phase": "idle",
    "detail": "",
    "step": 0,
    "total_steps": 0,
    "lines": [],
    "preview": "",
    "started_at": None,
    "updated_at": None,
}


def _now() -> float:
    return time.time()


def begin(job: str, *, total_steps: int = 0, detail: str = "") -> None:
    with _lock:
        _state.update(
            {
                "active": True,
                "job": str(job or "turn"),
                "phase": "start",
                "detail": str(detail or "Starting model work…"),
                "step": 0,
                "total_steps": max(0, int(total_steps or 0)),
                "lines": [],
                "preview": "",
                "started_at": _now(),
                "updated_at": _now(),
            }
        )


def update(
    phase: str,
    detail: str = "",
    *,
    step: int | None = None,
    total_steps: int | None = None,
    line: str | None = None,
) -> None:
    with _lock:
        if not _state.get("active"):
            # Allow opportunistic updates if a job forgot begin(); still useful.
            _state["active"] = True
            _state["started_at"] = _state.get("started_at") or _now()
            _state["lines"] = list(_state.get("lines") or [])
        _state["phase"] = str(phase or _state.get("phase") or "working")
        if detail:
            _state["detail"] = str(detail)
        if step is not None:
            _state["step"] = int(step)
        if total_steps is not None:
            _state["total_steps"] = max(0, int(total_steps))
        if line:
            lines = list(_state.get("lines") or [])
            text = str(line).strip()
            if text and (not lines or lines[-1] != text):
                lines.append(text)
                _state["lines"] = lines[-24:]
        _state["updated_at"] = _now()


def set_preview(text: str, *, append_paragraph: bool = False) -> None:
    clean = str(text or "").strip()
    with _lock:
        if append_paragraph and clean:
            existing = str(_state.get("preview") or "").strip()
            _state["preview"] = f"{existing}\n\n{clean}".strip() if existing else clean
        else:
            _state["preview"] = clean
        _state["updated_at"] = _now()


def end(*, detail: str = "Done.") -> None:
    with _lock:
        _state["active"] = False
        _state["phase"] = "done"
        if detail:
            _state["detail"] = str(detail)
        _state["updated_at"] = _now()


def fail(detail: str) -> None:
    with _lock:
        _state["active"] = False
        _state["phase"] = "error"
        _state["detail"] = str(detail or "Generation failed.")
        _state["updated_at"] = _now()


def snapshot() -> dict[str, Any]:
    with _lock:
        started = _state.get("started_at")
        updated = _state.get("updated_at")
        now = _now()
        elapsed = int(max(0, now - float(started))) if started else 0
        return {
            "active": bool(_state.get("active")),
            "job": str(_state.get("job") or ""),
            "phase": str(_state.get("phase") or "idle"),
            "detail": str(_state.get("detail") or ""),
            "step": int(_state.get("step") or 0),
            "total_steps": int(_state.get("total_steps") or 0),
            "lines": list(_state.get("lines") or []),
            "preview": str(_state.get("preview") or ""),
            "elapsed_seconds": elapsed,
            "started_at": started,
            "updated_at": updated,
        }
