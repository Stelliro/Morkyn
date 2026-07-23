"""Serialize GPU-heavy LLM and image work unless VRAM headroom allows overlap."""

from __future__ import annotations

import os
import subprocess
import threading
import time
from contextlib import contextmanager
from typing import Any, Iterator


_lock = threading.RLock()
_condition = threading.Condition(_lock)
_active: dict[str, float] = {}  # job_type -> start time
_DEFAULT_HEADROOM_MB = 8192  # free VRAM needed to allow parallel LLM+image


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def vram_status() -> dict[str, Any]:
    """Best-effort NVIDIA free/total VRAM in MiB (empty if unavailable)."""
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=memory.free,memory.total",
                "--format=csv,noheader,nounits",
            ],
            stderr=subprocess.DEVNULL,
            timeout=3,
            text=True,
        )
        line = (out or "").strip().splitlines()[0]
        free_s, total_s = [p.strip() for p in line.split(",")]
        free_mb = int(float(free_s))
        total_mb = int(float(total_s))
        return {"ok": True, "free_mb": free_mb, "total_mb": total_mb}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "free_mb": None, "total_mb": None}


def allow_parallel(job_type: str = "probe") -> bool:
    """
    Whether a different job type may overlap (LLM + image).
    - AI_RPG_GPU_FORCE_SERIAL=1 → never parallel
    - else if free VRAM >= AI_RPG_GPU_HEADROOM_MB (default 8192) → parallel OK
    - if nvidia-smi missing → serial (safe)
    """
    if _env_bool("AI_RPG_GPU_FORCE_SERIAL", False):
        return False
    if _env_bool("AI_RPG_GPU_ALLOW_PARALLEL", False):
        return True
    if not _env_bool("AI_RPG_GPU_AUTO_PARALLEL", True):
        return False
    headroom = _env_int("AI_RPG_GPU_HEADROOM_MB", _DEFAULT_HEADROOM_MB)
    status = vram_status()
    if not status.get("ok"):
        return False
    free_mb = int(status.get("free_mb") or 0)
    return free_mb >= headroom


def gate_status() -> dict[str, Any]:
    with _lock:
        active = {k: round(time.time() - t, 1) for k, t in _active.items()}
    vram = vram_status()
    return {
        "active": active,
        "vram": vram,
        "allow_parallel_now": allow_parallel(),
        "headroom_mb": _env_int("AI_RPG_GPU_HEADROOM_MB", _DEFAULT_HEADROOM_MB),
        "auto_parallel": _env_bool("AI_RPG_GPU_AUTO_PARALLEL", True),
        "force_serial": _env_bool("AI_RPG_GPU_FORCE_SERIAL", False),
    }


@contextmanager
def gpu_session(job_type: str, *, wait: bool = True, timeout: float | None = None) -> Iterator[dict[str, Any]]:
    """
    Coordinate GPU-heavy work.
    - Same job type always waits (no two images / two LLM gens at once).
    - LLM vs image: wait for each other unless allow_parallel() (VRAM headroom).
    """
    job_type = str(job_type or "gpu").strip().lower() or "gpu"
    started_wait = time.time()
    deadline = None if timeout is None else started_wait + max(1.0, float(timeout))
    meta: dict[str, Any] = {"job": job_type, "waited_s": 0.0, "exclusive": True}

    with _condition:
        while True:
            same_busy = job_type in _active
            rivals = {k for k in _active if k != job_type}
            if same_busy:
                can_start = False
            elif rivals and not allow_parallel(job_type):
                can_start = False
            else:
                can_start = True
                if rivals:
                    meta["exclusive"] = False
            if can_start:
                break
            if not wait:
                raise RuntimeError(
                    f"GPU busy with {sorted(_active.keys())}; cannot start {job_type}."
                )
            if deadline is not None and time.time() >= deadline:
                raise TimeoutError(
                    f"Timed out waiting for GPU (active={sorted(_active.keys())}) for {job_type}."
                )
            _condition.wait(timeout=0.5)
        _active[job_type] = time.time()
        meta["waited_s"] = round(time.time() - started_wait, 2)
        meta["vram"] = vram_status()

    try:
        yield meta
    finally:
        with _condition:
            _active.pop(job_type, None)
            _condition.notify_all()
