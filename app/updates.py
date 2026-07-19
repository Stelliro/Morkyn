"""
Optional, user-initiated update / rollback against the GitHub remote.

Never runs unless the user hits check/apply/rollback APIs.
Network targets: git remote (GitHub) only.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
HISTORY_PATH = ROOT / "data" / "update_history.json"
DEFAULT_REMOTE = "origin"
DEFAULT_GITHUB_REPO = "Stelliro/Morkyn"


def _run_git(args: list[str], timeout: int = 120) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()
    except FileNotFoundError:
        return 127, "", "git executable not found on PATH"
    except subprocess.TimeoutExpired:
        return 124, "", "git command timed out"


def _load_history() -> dict[str, Any]:
    if not HISTORY_PATH.is_file():
        return {"events": [], "last_known_good": None}
    try:
        raw = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            raw.setdefault("events", [])
            return raw
    except (OSError, json.JSONDecodeError):
        pass
    return {"events": [], "last_known_good": None}


def _save_history(history: dict[str, Any]) -> None:
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(json.dumps(history, ensure_ascii=True, indent=2), encoding="utf-8")


def _record_event(kind: str, detail: dict[str, Any]) -> None:
    history = _load_history()
    events = history.setdefault("events", [])
    events.append({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "kind": kind, **detail})
    history["events"] = events[-40:]
    _save_history(history)


def current_status() -> dict[str, Any]:
    code, head, err = _run_git(["rev-parse", "HEAD"])
    if code != 0:
        return {
            "ok": False,
            "error": err or "not a git checkout",
            "git_available": code != 127,
            "phone_home": False,
            "note": "Updates require a git clone of the project.",
        }
    _, branch, _ = _run_git(["rev-parse", "--abbrev-ref", "HEAD"])
    _, describe, _ = _run_git(["describe", "--tags", "--always", "--dirty"])
    _, remote_url, _ = _run_git(["config", "--get", f"remote.{DEFAULT_REMOTE}.url"])
    _, status_porcelain, _ = _run_git(["status", "--porcelain"])
    dirty = bool(status_porcelain.strip())
    history = _load_history()
    return {
        "ok": True,
        "git_available": True,
        "phone_home": False,
        "head": head[:12] if head else "",
        "head_full": head,
        "branch": branch,
        "describe": describe,
        "remote": DEFAULT_REMOTE,
        "remote_url": remote_url,
        "dirty": dirty,
        "last_known_good": history.get("last_known_good"),
        "recent_events": (history.get("events") or [])[-8:],
        "privacy": "Update check/apply only contacts GitHub when you request it. No analytics.",
    }


def _github_repo_from_remote(remote_url: str) -> str:
    url = (remote_url or "").strip()
    m = re.search(r"github\.com[:/](?P<repo>[^/]+/[^/.]+)(?:\.git)?$", url)
    if m:
        return m.group("repo")
    return os.getenv("AI_RPG_GITHUB_REPO", DEFAULT_GITHUB_REPO)


def check_for_updates() -> dict[str, Any]:
    """User-initiated: git fetch + optional GitHub latest release lookup."""
    status = current_status()
    if not status.get("ok"):
        return status

    code, out, err = _run_git(["fetch", DEFAULT_REMOTE, "--tags", "--prune"], timeout=180)
    if code != 0:
        _record_event("check_failed", {"error": err or out})
        return {**status, "ok": False, "error": err or out or "git fetch failed", "phone_home": True}

    _, local_head, _ = _run_git(["rev-parse", "HEAD"])
    _, remote_head, _ = _run_git(["rev-parse", f"{DEFAULT_REMOTE}/main"])
    if remote_head.startswith("fatal") or not remote_head:
        _, remote_head, _ = _run_git(["rev-parse", f"{DEFAULT_REMOTE}/master"])

    ahead = behind = None
    if remote_head and not remote_head.startswith("fatal"):
        _, counts, _ = _run_git(["rev-list", "--left-right", "--count", f"HEAD...{remote_head}"])
        parts = counts.split()
        if len(parts) == 2:
            ahead, behind = int(parts[0]), int(parts[1])

    release: dict[str, Any] | None = None
    repo = _github_repo_from_remote(str(status.get("remote_url") or ""))
    try:
        req = urllib.request.Request(
            f"https://api.github.com/repos/{repo}/releases/latest",
            headers={"Accept": "application/vnd.github+json", "User-Agent": "Morkyn-Updater"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        if isinstance(payload, dict) and payload.get("tag_name"):
            release = {
                "tag": payload.get("tag_name"),
                "name": payload.get("name"),
                "url": payload.get("html_url"),
                "published_at": payload.get("published_at"),
            }
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        release = {"error": f"GitHub releases lookup skipped or failed: {exc}"}

    result = {
        **status,
        "ok": True,
        "phone_home": True,
        "fetched": True,
        "local_head": (local_head or "")[:12],
        "remote_head": (remote_head or "")[:12] if remote_head and not str(remote_head).startswith("fatal") else "",
        "ahead": ahead,
        "behind": behind,
        "update_available": bool(behind and behind > 0),
        "latest_release": release,
        "message": (
            f"Remote is {behind} commit(s) ahead." if behind and behind > 0
            else "Already up to date with remote default branch (or remote not found)."
        ),
    }
    _record_event("check", {"behind": behind, "ahead": ahead, "remote_head": result.get("remote_head")})
    return result


def _refuse_if_dirty() -> str | None:
    _, porcelain, _ = _run_git(["status", "--porcelain"])
    if porcelain.strip():
        return "Working tree has local changes. Commit, stash, or clean them before update/rollback."
    return None


def apply_update(target: str = "") -> dict[str, Any]:
    """
    User-initiated apply.
    target empty => merge origin/main (or master)
    target tag/commit => checkout that ref (detached ok for tags; we try to stay on branch for main)
    """
    status = current_status()
    if not status.get("ok"):
        return status
    dirty = _refuse_if_dirty()
    if dirty:
        return {**status, "ok": False, "error": dirty, "phone_home": False}

    _, head_before, _ = _run_git(["rev-parse", "HEAD"])
    history = _load_history()
    history["last_known_good"] = {
        "head": head_before,
        "describe": status.get("describe"),
        "branch": status.get("branch"),
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    _save_history(history)

    code, _, err = _run_git(["fetch", DEFAULT_REMOTE, "--tags", "--prune"], timeout=180)
    if code != 0:
        _record_event("apply_failed", {"error": err, "stage": "fetch"})
        return {**status, "ok": False, "error": err or "fetch failed", "phone_home": True}

    ref = (target or "").strip()
    if not ref:
        # Prefer main
        for candidate in (f"{DEFAULT_REMOTE}/main", f"{DEFAULT_REMOTE}/master"):
            c, h, _ = _run_git(["rev-parse", candidate])
            if c == 0 and h:
                ref = candidate
                break
        if not ref:
            return {**status, "ok": False, "error": "Could not resolve origin/main or origin/master", "phone_home": True}
        code, out, err = _run_git(["merge", "--ff-only", ref], timeout=180)
        action = "merge --ff-only"
    else:
        # Safe-ish refs only
        if not re.fullmatch(r"[A-Za-z0-9._/\-]+", ref):
            return {**status, "ok": False, "error": "Invalid target ref", "phone_home": False}
        code, out, err = _run_git(["checkout", ref], timeout=120)
        action = f"checkout {ref}"

    if code != 0:
        _record_event("apply_failed", {"error": err or out, "action": action})
        return {**status, "ok": False, "error": err or out or "update failed", "phone_home": True, "action": action}

    _, head_after, _ = _run_git(["rev-parse", "HEAD"])
    _, describe, _ = _run_git(["describe", "--tags", "--always"])
    _record_event(
        "apply",
        {"from": head_before[:12], "to": (head_after or "")[:12], "action": action, "describe": describe},
    )
    return {
        "ok": True,
        "phone_home": True,
        "action": action,
        "from": head_before[:12],
        "to": (head_after or "")[:12],
        "describe": describe,
        "message": "Update applied. Restart the app/launcher to load new code.",
        "restart_required": True,
    }


def rollback(target: str = "") -> dict[str, Any]:
    """
    User-initiated rollback to last_known_good, or an explicit commit/tag.
    """
    status = current_status()
    if not status.get("ok"):
        return status
    dirty = _refuse_if_dirty()
    if dirty:
        return {**status, "ok": False, "error": dirty, "phone_home": False}

    history = _load_history()
    ref = (target or "").strip()
    if not ref:
        lkg = history.get("last_known_good") or {}
        ref = str(lkg.get("head") or "").strip()
        if not ref:
            return {
                **status,
                "ok": False,
                "error": "No last-known-good snapshot yet. Apply an update once first, or pass an explicit commit/tag.",
                "phone_home": False,
            }
    if not re.fullmatch(r"[A-Za-z0-9._/\-]+", ref):
        return {**status, "ok": False, "error": "Invalid rollback ref", "phone_home": False}

    _, head_before, _ = _run_git(["rev-parse", "HEAD"])
    code, out, err = _run_git(["checkout", ref], timeout=120)
    if code != 0:
        _record_event("rollback_failed", {"error": err or out, "ref": ref})
        return {**status, "ok": False, "error": err or out or "rollback failed", "phone_home": False}

    _, head_after, _ = _run_git(["rev-parse", "HEAD"])
    _, describe, _ = _run_git(["describe", "--tags", "--always"])
    _record_event("rollback", {"from": head_before[:12], "to": (head_after or "")[:12], "ref": ref, "describe": describe})
    return {
        "ok": True,
        "phone_home": False,
        "from": head_before[:12],
        "to": (head_after or "")[:12],
        "describe": describe,
        "message": "Rollback applied. Restart the app/launcher to load this version.",
        "restart_required": True,
    }
