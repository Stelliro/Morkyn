"""Versions: the packaged build's updater, where the player picks the version.

Stell (2026-10-19): "we will need a new method for updating, but we should
probbaly make it so the user can select a version, this is a future proofing
method i want to use." The app lists the GitHub releases, the player chooses
one, newer or older, and it is downloaded into ``versions/<tag>/`` under the
home (app.paths.ROOT). ``data/active_version.json`` names the chosen one; at
start the executable the player opened hands over to that version's executable
with ``MORKYN_HOME`` set, so every version shares ``data/`` and the runtime
packs. Choosing "this build" clears the handover.

Only a packaged build installs and hands over; a checkout updates with git
(app.updates) and uses this module to list releases.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tarfile
import threading
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from app.paths import ROOT

GITHUB_REPO = "Stelliro/Morkyn"
_PROGRESS: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()


def versions_dir() -> Path:
    return Path(os.getenv("MORKYN_VERSIONS_DIR") or (ROOT / "versions"))


def active_file() -> Path:
    return ROOT / "data" / "active_version.json"


def running_version() -> str:
    try:
        from app.main import APP_VERSION

        return str(APP_VERSION or "").lstrip("Vv")
    except Exception:
        return ""


def _norm(tag: str) -> str:
    return str(tag or "").strip().lstrip("Vv")


def os_tag() -> str:
    return {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")


def archive_matches(name: str) -> bool:
    """The release asset that is this platform's app build (packaging/build.*)."""
    low = str(name or "").lower()
    if not low.startswith("morkyn-"):
        return False
    if os_tag() == "windows":
        return low.endswith("-windows-x64.zip")
    if os_tag() == "macos":
        return low.endswith("-macos.zip")
    return low.endswith(".tar.gz") and "-linux-" in low


# --- what is installed ------------------------------------------------------

def exe_path(tag: str) -> Path | None:
    """The executable of an installed version, or None."""
    base = versions_dir() / _norm(tag)
    if not base.is_dir():
        return None
    candidates = [
        base / "Morkyn" / "Morkyn.exe",
        base / "Morkyn.exe",
        base / "Morkyn.app" / "Contents" / "MacOS" / "Morkyn",
        base / "Morkyn" / "Morkyn",
        base / "Morkyn",
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def installed_versions() -> list[str]:
    base = versions_dir()
    if not base.is_dir():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_dir() and exe_path(p.name) is not None)


def active_tag() -> str:
    try:
        data = json.loads(active_file().read_text(encoding="utf-8"))
        return _norm(data.get("tag") or "") if isinstance(data, dict) else ""
    except Exception:
        return ""


def set_active(tag: str) -> dict[str, Any]:
    """Name the version to hand over to at the next start; "" means this build."""
    tag = _norm(tag)
    if tag and exe_path(tag) is None:
        return {"ok": False, "error": f"{tag} is not installed"}
    path = active_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"tag": tag, "set_at": time.strftime("%Y-%m-%dT%H:%M:%S")}, indent=2), encoding="utf-8")
    return {"ok": True, "tag": tag, "note": "Takes effect at the next start of Mørkyn."}


def handover_target() -> Path | None:
    """The executable the home build should run instead of itself, or None."""
    if not getattr(sys, "frozen", False) or os.getenv("MORKYN_NO_HANDOVER"):
        return None
    tag = active_tag()
    if not tag or tag == running_version():
        return None
    target = exe_path(tag)
    if target is None or target.resolve() == Path(sys.executable).resolve():
        return None
    return target


def hand_over(argv: list[str]) -> int | None:
    """Start the active version with this home; None when this build should run itself.

    A target that dies within a few seconds is not trusted: the choice is
    cleared and this build runs, so a broken download never locks the player out.
    """
    target = handover_target()
    if target is None:
        return None
    env = {**os.environ, "MORKYN_HOME": str(ROOT), "MORKYN_NO_HANDOVER": "1"}
    try:
        proc = subprocess.Popen([str(target), *argv], cwd=str(target.parent), env=env)
    except Exception:
        set_active("")
        return None
    try:
        code = proc.wait(timeout=6)
    except subprocess.TimeoutExpired:
        return 0  # it is running; this process is done
    if code != 0:
        set_active("")
        return None
    return 0


# --- the releases -----------------------------------------------------------

def list_releases(limit: int = 30, check_online: bool = True) -> dict[str, Any]:
    releases: list[dict[str, Any]] = []
    error = ""
    if check_online:
        try:
            req = urllib.request.Request(
                f"https://api.github.com/repos/{GITHUB_REPO}/releases?per_page={int(limit)}",
                headers={"Accept": "application/vnd.github+json", "User-Agent": "Morkyn-Versions"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            for rel in payload if isinstance(payload, list) else []:
                tag = _norm(rel.get("tag_name") or "")
                if not tag or tag == "runtime-packs":
                    continue
                asset = next(({"name": a.get("name"), "url": a.get("browser_download_url"), "size": int(a.get("size") or 0)}
                              for a in rel.get("assets") or [] if isinstance(a, dict) and archive_matches(str(a.get("name") or ""))),
                             None)
                releases.append({
                    "tag": tag,
                    "name": rel.get("name") or tag,
                    "published_at": rel.get("published_at"),
                    "prerelease": bool(rel.get("prerelease")),
                    "url": rel.get("html_url"),
                    "asset": asset,
                })
        except Exception as exc:
            error = f"GitHub releases lookup failed: {exc.__class__.__name__}: {exc}"[:200]
    have = set(installed_versions())
    active = active_tag()
    running = running_version()
    known = {r["tag"] for r in releases}
    for tag in sorted(have - known):
        releases.append({"tag": tag, "name": tag, "published_at": None, "prerelease": None, "url": None, "asset": None})
    for rel in releases:
        rel["installed"] = rel["tag"] in have
        rel["active"] = rel["tag"] == active
        rel["running"] = rel["tag"] == running
        rel["progress"] = _PROGRESS.get(rel["tag"])
    return {
        "packaged": bool(getattr(sys, "frozen", False)),
        "running": running,
        "active": active,
        "home": str(ROOT),
        "versions_dir": str(versions_dir()),
        "releases": releases,
        "error": error,
    }


# --- install / remove -------------------------------------------------------

def _set_progress(tag: str, **fields: Any) -> None:
    with _LOCK:
        entry = _PROGRESS.setdefault(tag, {})
        entry.update(fields)
        entry["at"] = time.time()


def _download(url: str, dest: Path, tag: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "Morkyn-Versions"})
    with urllib.request.urlopen(req, timeout=60) as resp, dest.open("wb") as fh:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            fh.write(chunk)
            done += len(chunk)
            _set_progress(tag, state="downloading", bytes=done, total=total)


def _extract(archive: Path, target: Path) -> None:
    tmp = target.with_name(target.name + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    if archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(tmp)
    else:
        with tarfile.open(archive, "r:gz") as tf:
            tf.extractall(tmp)
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    tmp.rename(target)
    if os.name != "nt":
        for exe in (target / "Morkyn" / "Morkyn", target / "Morkyn.app" / "Contents" / "MacOS" / "Morkyn"):
            if exe.is_file():
                exe.chmod(exe.stat().st_mode | 0o755)


def install(tag: str, url: str | None = None, *, wait: bool = False) -> dict[str, Any]:
    """Download a release's app build for this platform into versions/<tag>/ (threaded unless ``wait``)."""
    tag = _norm(tag)
    if not tag:
        return {"ok": False, "error": "no version named"}
    if url is None:
        rel = next((r for r in list_releases().get("releases") or [] if r["tag"] == tag), None)
        url = str(((rel or {}).get("asset") or {}).get("url") or "")
        name = str(((rel or {}).get("asset") or {}).get("name") or "")
    else:
        name = url.rsplit("/", 1)[-1]
    if not url:
        return {"ok": False, "error": f"no build of {tag} for {os_tag()} on the release"}
    current = _PROGRESS.get(tag) or {}
    if current.get("state") in {"downloading", "unpacking"}:
        return {"ok": True, "already": True}

    def work() -> None:
        try:
            _set_progress(tag, state="downloading", bytes=0, total=0, error="")
            archive = versions_dir() / ".downloads" / (name or f"{tag}.zip")
            _download(url, archive, tag)
            _set_progress(tag, state="unpacking")
            _extract(archive, versions_dir() / tag)
            if exe_path(tag) is None:
                raise ValueError("the archive holds no Mørkyn executable")
            (versions_dir() / tag / "version.json").write_text(
                json.dumps({"tag": tag, "installed_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "asset": name}, indent=2),
                encoding="utf-8",
            )
            try:
                archive.unlink()
            except Exception:
                pass
            _set_progress(tag, state="installed")
        except Exception as exc:
            _set_progress(tag, state="failed", error=f"{exc.__class__.__name__}: {exc}"[:300])

    if wait:
        work()
        return {"ok": _PROGRESS.get(tag, {}).get("state") == "installed", **(_PROGRESS.get(tag) or {})}
    threading.Thread(target=work, daemon=True, name=f"version-{tag}").start()
    return {"ok": True, "started": True}


def remove(tag: str) -> dict[str, Any]:
    tag = _norm(tag)
    folder = versions_dir() / tag
    if not folder.is_dir():
        return {"ok": False, "error": "not installed"}
    if tag == active_tag():
        set_active("")
    shutil.rmtree(folder, ignore_errors=True)
    _PROGRESS.pop(tag, None)
    return {"ok": True}
