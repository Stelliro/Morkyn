"""One-click local models: a short list of GGUFs known to load, downloaded into MLE's folder.

Stell (2026-10-23): "is it possible to add a one click install to a good 8b
model?" The list is short on purpose. A model on it has a fixed file, size and
SHA-256 from its Hugging Face repo, a context window the story contract fits
in (12288 tokens or more), and an architecture the pinned llama-cpp-python
loads. Hermes 3 (Llama 3.1 8B) is the recommended one, Stell's pick ("expecting
less and getting more is our goal anyway"); Qwen3 8B is the model the 8B runs
were measured on, kept so the baseline is one click away.

A download goes to ``<name>.part`` beside the others, resumes from where it
stopped (HTTP Range), is checked against its SHA-256 and only then renamed to
its ``.gguf`` name, so a cut download never looks like a model. ``use()`` sets
the engine to MLE with that file.
"""
from __future__ import annotations

import hashlib
import shutil
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any

from app.mle import models_dir

CATALOG: list[dict[str, Any]] = [
    {
        "id": "hermes-3-llama-3.1-8b",
        "title": "Hermes 3 (Llama 3.1 8B)",
        "summary": "Natural prose and a steady character voice; 128K context. Nous Research's Llama 3.1 tune.",
        "repo": "NousResearch/Hermes-3-Llama-3.1-8B-GGUF",
        "file": "Hermes-3-Llama-3.1-8B.Q4_K_M.gguf",
        "size": 4920733824,
        "sha256": "d4403ce5a6e930f4c2509456388c20d633a15ff08dd52ef3b142ff1810ec3553",
        "recommended": True,
    },
    {
        "id": "llama-3.1-8b-instruct",
        "title": "Llama 3.1 8B Instruct",
        "summary": "Meta's own Llama 3.1 8B, without a story tune; 128K context.",
        "repo": "bartowski/Meta-Llama-3.1-8B-Instruct-GGUF",
        "file": "Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf",
        "size": 4920739232,
        "sha256": "7b064f5842bf9532c91456deda288a1b672397a54fa729aa665952863033557c",
    },
    {
        "id": "qwen3-8b",
        "title": "Qwen3 8B",
        "summary": "The model Mørkyn's 8B test runs were measured on; the baseline to compare against.",
        "repo": "Qwen/Qwen3-8B-GGUF",
        "file": "Qwen3-8B-Q4_K_M.gguf",
        "size": 5027783488,
        "sha256": "d98cdcbd03e17ce47681435b5150e34c1417f50b5c0019dd560e4882c5745785",
    },
]

_PROGRESS: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()
_CHUNK = 1 << 20


def entry(model_id: str) -> dict[str, Any] | None:
    return next((dict(e) for e in CATALOG if e["id"] == model_id), None)


def url_for(item: dict[str, Any]) -> str:
    return f"https://huggingface.co/{item['repo']}/resolve/main/{item['file']}"


def _target(item: dict[str, Any]) -> Path:
    return models_dir() / item["file"]


def _part(item: dict[str, Any]) -> Path:
    return models_dir() / (item["file"] + ".part")


def _set(model_id: str, **fields: Any) -> None:
    with _LOCK:
        current = dict(_PROGRESS.get(model_id) or {})
        current.update(fields)
        current["at"] = time.time()
        _PROGRESS[model_id] = current


def status() -> dict[str, Any]:
    """The catalog with what is on disk, what is downloading, and the free space where models go."""
    from app.launcher_prefs import load_prefs

    current = str(load_prefs().get("mle_model") or "")
    folder = models_dir()
    free = 0
    try:
        folder.mkdir(parents=True, exist_ok=True)
        free = shutil.disk_usage(folder).free
    except OSError:
        pass
    models = []
    for item in CATALOG:
        target, part = _target(item), _part(item)
        installed = target.is_file() and target.stat().st_size == item["size"]
        partial = part.stat().st_size if part.is_file() else 0
        models.append({
            **item,
            "url": url_for(item),
            "installed": installed,
            "partial": partial,
            "in_use": installed and current in {item["file"], item["file"].removesuffix(".gguf"), str(target)},
            "progress": dict(_PROGRESS.get(item["id"]) or {}),
        })
    return {"folder": str(folder), "free": free, "models": models}


def _hash_existing(path: Path) -> "hashlib._Hash":
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(_CHUNK), b""):
            digest.update(block)
    return digest


def download(item: dict[str, Any], url: str | None = None) -> Path:
    """Fetch the model into its .part file (resuming), check the SHA-256, and rename it into place."""
    model_id = item["id"]
    target, part = _target(item), _part(item)
    target.parent.mkdir(parents=True, exist_ok=True)
    have = part.stat().st_size if part.is_file() else 0
    if have > item["size"]:
        part.unlink()
        have = 0
    need = item["size"] - have
    free = shutil.disk_usage(target.parent).free
    if free < need + (256 << 20):
        raise OSError(f"{need / 2**30:.1f} GB more is needed in {target.parent}; {free / 2**30:.1f} GB is free")
    _set(model_id, state="checking" if have else "downloading", bytes=have, total=item["size"], error="")
    digest = _hash_existing(part) if have else hashlib.sha256()
    if have < item["size"]:
        req = urllib.request.Request(url or url_for(item), headers={"User-Agent": "Morkyn-Models"})
        if have:
            req.add_header("Range", f"bytes={have}-")
        with urllib.request.urlopen(req, timeout=60) as resp:
            if have and getattr(resp, "status", 200) != 206:
                # The server ignored the range: start over rather than append the file again.
                have, digest = 0, hashlib.sha256()
                part.unlink(missing_ok=True)
            with part.open("ab") as fh:
                while True:
                    chunk = resp.read(_CHUNK)
                    if not chunk:
                        break
                    fh.write(chunk)
                    digest.update(chunk)
                    have += len(chunk)
                    _set(model_id, state="downloading", bytes=have, total=item["size"])
    _set(model_id, state="checking", bytes=have, total=item["size"])
    if have != item["size"] or digest.hexdigest() != item["sha256"]:
        part.unlink(missing_ok=True)
        raise ValueError("the download did not match its checksum and was removed; try again")
    part.replace(target)
    return target


def install(model_id: str, *, wait: bool = False, url: str | None = None) -> dict[str, Any]:
    """Download a catalog model (in a thread unless ``wait``). Progress is read from status()."""
    item = entry(model_id)
    if item is None:
        return {"ok": False, "error": f"unknown model {model_id!r}"}
    if (_PROGRESS.get(model_id) or {}).get("state") in {"downloading", "checking"}:
        return {"ok": True, "already": True}
    if _target(item).is_file() and _target(item).stat().st_size == item["size"]:
        return {"ok": True, "installed": True}

    def work() -> None:
        try:
            download(item, url)
            _set(model_id, state="installed")
        except Exception as exc:
            _set(model_id, state="failed", error=f"{exc.__class__.__name__}: {exc}"[:300])

    _set(model_id, state="downloading", bytes=0, total=item["size"], error="")
    if wait:
        work()
        return {"ok": _PROGRESS[model_id].get("state") == "installed", **_PROGRESS[model_id]}
    threading.Thread(target=work, daemon=True, name=f"model-{model_id}").start()
    return {"ok": True, "started": True}


def use(model_id: str) -> dict[str, Any]:
    """Make an installed catalog model the one MLE runs: the launcher prefs, the live env and the model settings."""
    from app.launcher_prefs import apply_prefs_to_env, save_prefs
    from app.llm import update_model_config

    item = entry(model_id)
    if item is None:
        return {"ok": False, "error": f"unknown model {model_id!r}"}
    if not _target(item).is_file():
        return {"ok": False, "error": f"{item['title']} is not installed"}
    apply_prefs_to_env(save_prefs({"model_provider": "mle", "mle_model": item["file"]}))
    update_model_config({"provider": "mle", "mle_model": item["file"]})
    return {"ok": True, "note": f"{item['title']} is the model now; it loads on the next turn."}


def remove(model_id: str) -> dict[str, Any]:
    item = entry(model_id)
    if item is None:
        return {"ok": False, "error": f"unknown model {model_id!r}"}
    for path in (_target(item), _part(item)):
        path.unlink(missing_ok=True)
    _PROGRESS.pop(model_id, None)
    return {"ok": True}
