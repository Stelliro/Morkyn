"""Runtime packs: the heavy dependencies the packaged app does not ship with.

Stell (2026-10-19): "could we make the exe seperate from its dependancies so we
dont ship them together?" and "we need hardware specific auto installs as well
as an area the user can select what they want and if they want to use a custom
one". The app build carries Python, the game and the web files. llama-cpp-python
is a *pack*: a zip built per platform, Python tag and accelerator (CUDA, CPU,
Metal, Vulkan), attached to the GitHub release tagged ``runtime-packs``, and
downloaded into ``runtime/<id>/`` beside the executable. Packs are shared by
every installed app version (they sit under the home, app.paths.ROOT).

The choice is the launcher pref ``engine_pack``: ``auto`` (the pack that fits
the hardware, app.hardware; installed on its own at the first start that needs
it), a pack id, ``custom`` (a folder or zip of the player's own build, pref
``engine_pack_custom``) or ``none``. ``activate()`` puts the chosen engine on
``sys.path`` at every start; every process of the app runs it.

A pack zip holds ``pack.json`` ({id, version, python_tag, os, arch, built}) and
``site/`` (the installed packages). packaging/build_packs.py makes them.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import sys
import threading
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from app.paths import ROOT

PACK_RELEASE_TAG = "runtime-packs"
GITHUB_REPO = "Stelliro/Morkyn"

CATALOG: list[dict[str, Any]] = [
    {
        "id": "llama-cpp-cuda",
        "title": "llama.cpp engine, NVIDIA CUDA 12.4",
        "summary": "Runs GGUF models on an NVIDIA GPU: the local narrator (MLE) and the managed llama.cpp server. About 790 MB.",
        "os": ["windows", "linux"],
        "provides": "llama_cpp",
    },
    {
        "id": "llama-cpp-metal",
        "title": "llama.cpp engine, Apple Metal",
        "summary": "Runs GGUF models on an Apple Silicon GPU.",
        "os": ["macos"],
        "provides": "llama_cpp",
    },
    {
        "id": "llama-cpp-vulkan",
        "title": "llama.cpp engine, Vulkan",
        "summary": "Runs GGUF models on AMD, Intel and NVIDIA GPUs through Vulkan.",
        "os": ["windows", "linux"],
        "provides": "llama_cpp",
    },
    {
        "id": "llama-cpp-cpu",
        "title": "llama.cpp engine, CPU",
        "summary": "Runs GGUF models on the processor only. Small models or patience; about 60 MB.",
        "os": ["windows", "linux", "macos"],
        "provides": "llama_cpp",
    },
    # Add-ons sit beside the engine: every installed one is on the path. The
    # packaged app has no pip, and "Install local speech engine" ran
    # `Morkyn.exe -m pip ...`, which opened a second Mørkyn (Stell, 2026-10-22).
    {
        "id": "piper-speech",
        "title": "Local speech engine (Piper)",
        "summary": "Reads the story aloud on this machine, no account needed. Voices download separately in Speech settings.",
        "os": ["windows", "linux", "macos"],
        "provides": "piper",
        "kind": "addon",
    },
    # Linux has no web view of its own for Python: without this the game opens
    # in the browser (Stell, 2026-10-23, on Pop!_OS: "it doesnt have a
    # standalone application on linux"). pywebview with Qt WebEngine is all
    # pip wheels, so it needs nothing from the distribution.
    {
        "id": "qt-window",
        "title": "Mørkyn window (Qt WebEngine)",
        "summary": "Opens the game in its own window instead of the browser. About 200 MB; fetched on its own the first time the window is needed.",
        "os": ["linux"],
        "provides": "webview",
        "kind": "addon",
    },
]


def is_addon(pack_id: str) -> bool:
    return any(e["id"] == pack_id and e.get("kind") == "addon" for e in CATALOG)

_PROGRESS: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()
_ASSET_CACHE: dict[str, Any] = {"at": 0.0, "assets": {}}


# --- naming -----------------------------------------------------------------

def os_tag() -> str:
    return {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")


def arch_tag() -> str:
    machine = platform.machine().lower()
    if machine in {"x86_64", "amd64", "x64"}:
        return "x64"
    if machine in {"arm64", "aarch64"}:
        return "arm64"
    return machine or "unknown"


def python_tag() -> str:
    return f"cp{sys.version_info[0]}{sys.version_info[1]}"


def asset_name(pack_id: str) -> str:
    return f"morkyn-pack-{pack_id}-{os_tag()}-{arch_tag()}-{python_tag()}.zip"


def packs_dir() -> Path:
    return Path(os.getenv("MORKYN_RUNTIME_DIR") or (ROOT / "runtime"))


def catalog_here() -> list[dict[str, Any]]:
    return [dict(e) for e in CATALOG if os_tag() in e["os"]]


# --- the choice -------------------------------------------------------------

def _prefs() -> dict[str, Any]:
    try:
        from app.launcher_prefs import load_prefs

        return load_prefs()
    except Exception:
        return {"engine_pack": "auto", "engine_pack_custom": ""}


def choice() -> dict[str, Any]:
    """{mode, pack, custom, why}: what the player chose, resolved to a pack id for auto."""
    prefs = _prefs()
    mode = str(prefs.get("engine_pack") or "auto")
    custom = str(prefs.get("engine_pack_custom") or "")
    if mode == "auto":
        try:
            from app.hardware import recommended_pack

            pack, why = recommended_pack()
        except Exception:
            pack, why = "llama-cpp-cpu", "hardware detection failed: the CPU build"
        if pack not in {e["id"] for e in catalog_here()}:
            pack, why = "llama-cpp-cpu", f"{pack} is not built for {os_tag()}: the CPU build"
        return {"mode": "auto", "pack": pack, "custom": "", "why": why}
    if mode == "custom":
        return {"mode": "custom", "pack": "", "custom": custom, "why": "the player's own build"}
    if mode == "none":
        return {"mode": "none", "pack": "", "custom": "", "why": "no local engine"}
    return {"mode": "pack", "pack": mode, "custom": "", "why": "chosen by the player"}


def set_choice(mode: str, custom: str = "") -> dict[str, Any]:
    from app.launcher_prefs import ENGINE_PACK_CHOICES, load_prefs, save_prefs

    mode = str(mode or "auto").strip().lower()
    if mode not in ENGINE_PACK_CHOICES:
        return {"ok": False, "error": f"unknown choice {mode!r}"}
    if mode == "custom":
        custom = str(custom or "").strip()
        if not custom or not Path(custom).expanduser().exists():
            return {"ok": False, "error": "the custom engine needs an existing folder or zip"}
    prefs = load_prefs()
    prefs["engine_pack"] = mode
    prefs["engine_pack_custom"] = custom if mode == "custom" else str(prefs.get("engine_pack_custom") or "")
    save_prefs(prefs)
    return {"ok": True, "choice": choice(), "note": "A changed engine loads at the next start of Mørkyn."}


# --- installed packs --------------------------------------------------------

def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def installed() -> list[dict[str, Any]]:
    """Every pack folder under runtime/ with a pack.json, in name order."""
    out: list[dict[str, Any]] = []
    base = packs_dir()
    if not base.is_dir():
        return out
    for folder in sorted(base.iterdir()):
        if folder.name in {"custom", ".downloads"} or folder.name.endswith(".tmp"):
            continue  # the custom engine's unpack area and downloads in flight are no packs
        meta = _read_json(folder / "pack.json")
        if not meta.get("id") or not (folder / "site").is_dir():
            continue
        out.append({**meta, "path": str(folder), "site": str(folder / "site"),
                    "fits": meta.get("python_tag") == python_tag() and meta.get("os", os_tag()) == os_tag()})
    return out


def boot_identity() -> dict[str, Any]:
    """What a server started now would run: the build and the installed packs.

    The server keeps the one it booted with; a launcher that finds a server
    already running compares it with its own and replaces a stale one. A
    server left behind by a closed window kept serving the old build without
    the packs installed since (Linux .deb, 2026-10-23, #147).
    """
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable)
        try:
            stat = exe.stat()
            build = f"{exe.resolve()}:{stat.st_size}:{stat.st_mtime_ns}"
        except OSError:
            build = str(exe)
    else:
        build = str(ROOT.resolve())  # a source checkout: edits do not make a running server stale
    packs = []
    try:
        for pack in installed():
            packs.append(f"{pack.get('id')}:{pack.get('built') or ''}:{pack.get('installed_at') or ''}")
    except Exception:
        pass
    return {"build": build, "packs": packs}


def _custom_site(custom: str) -> Path | None:
    """The importable folder of a custom engine: the folder itself, its site/, or a zip unpacked under runtime/custom/."""
    if not custom:
        return None
    path = Path(custom).expanduser()
    if path.is_dir():
        if (path / "llama_cpp").is_dir():
            return path
        if (path / "site" / "llama_cpp").is_dir():
            return path / "site"
        return path
    if path.is_file() and path.suffix.lower() == ".zip":
        target = packs_dir() / "custom"
        stamp = target / "source.json"
        meta = _read_json(stamp)
        if meta.get("source") != str(path) or meta.get("mtime") != path.stat().st_mtime or not target.is_dir():
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
            target.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(path) as zf:
                zf.extractall(target)
            stamp.write_text(json.dumps({"source": str(path), "mtime": path.stat().st_mtime}), encoding="utf-8")
        return target / "site" if (target / "site").is_dir() else target
    return None


def _add_site(site: Path, added: list[str]) -> None:
    text = str(site)
    if text not in sys.path:
        sys.path.insert(0, text)
        added.append(text)
    if os.name == "nt":
        # The wheel's DLLs sit beside the package; llama_cpp loads them by
        # full path, but a dependency of theirs may be looked up by name.
        for lib in list(site.glob("*/lib")) + list(site.glob("*/*/lib")):
            try:
                os.add_dll_directory(str(lib))
            except Exception:
                pass
        _preload_cuda(site)
    elif sys.platform.startswith("linux"):
        _preload_cuda(site)


# The Linux CUDA wheel of llama-cpp-python links libcudart.so.12 and cuBLAS
# but does not carry them, and a desktop with only the NVIDIA driver (Pop!_OS,
# 2026-10-23) has neither: "libcudart.so.12: cannot open shared object file".
# The Linux CUDA pack carries NVIDIA's own wheels (site/nvidia/*/lib); loading
# them by path first, RTLD_GLOBAL, lets libllama.so find them by soname.
# Order matters: cuBLAS needs cudart, and libcublas needs libcublasLt.
_CUDA_LIBS = ("cuda_runtime/lib/libcudart.so.12", "cublas/lib/libcublasLt.so.12", "cublas/lib/libcublas.so.12")
# Windows has the same gap (a player's 0.11.1 exe, 2026-10-28: llama.dll would
# not load on a PC with the driver and no CUDA Toolkit). llama_cpp loads its DLL
# with winmode=0, so a dependency is looked up by the standard order (PATH, not
# add_dll_directory); a DLL already loaded by full path is used by its name.
_CUDA_DLLS = ("cuda_runtime/bin/cudart64_12.dll", "cublas/bin/cublasLt64_12.dll", "cublas/bin/cublas64_12.dll")


def _preload_cuda(site: Path) -> None:
    import ctypes

    if sys.platform == "win32":
        for rel in _CUDA_DLLS:
            lib = site / "nvidia" / rel
            if lib.is_file():
                folder = str(lib.parent)
                if folder not in os.environ.get("PATH", "").split(os.pathsep):
                    os.environ["PATH"] = folder + os.pathsep + os.environ.get("PATH", "")
                try:
                    ctypes.WinDLL(str(lib))
                except OSError:
                    pass
        return
    for rel in _CUDA_LIBS:
        lib = site / "nvidia" / rel
        if lib.is_file():
            try:
                ctypes.CDLL(str(lib), mode=ctypes.RTLD_GLOBAL)
            except OSError:
                pass


def activate() -> list[str]:
    """Put the chosen engine on sys.path: the custom folder, else the chosen or auto pack. Returns the paths added."""
    added: list[str] = []
    picked = choice()
    try:
        for pack in installed():
            if pack.get("fits") and is_addon(str(pack.get("id") or "")):
                _add_site(Path(pack["site"]), added)
    except Exception:
        pass
    try:
        if picked["mode"] == "none":
            return added
        if picked["mode"] == "custom":
            site = _custom_site(picked["custom"])
            if site is not None:
                _add_site(site, added)
            return added
        have = {p["id"]: p for p in installed() if p.get("fits") and not is_addon(str(p.get("id") or ""))}
        pack = have.get(picked["pack"])
        if pack is None and picked["mode"] == "auto" and have:
            # Auto with the fitting pack not yet installed: any installed one serves until it is.
            pack = next(iter(have.values()))
        if pack is not None:
            _add_site(Path(pack["site"]), added)
    except Exception:
        pass
    return added


def provides(module: str) -> bool:
    """Whether ``module`` can be imported now (from the bundle, a pack or the environment)."""
    import importlib.util

    try:
        return importlib.util.find_spec(module) is not None
    except Exception:
        return False


# --- the release's assets ---------------------------------------------------

def available_assets(force: bool = False) -> dict[str, dict[str, Any]]:
    """{asset name: {url, size}} of the runtime-packs release, cached ten minutes; {} when offline."""
    with _LOCK:
        if not force and time.time() - float(_ASSET_CACHE["at"]) < 600 and _ASSET_CACHE["assets"]:
            return dict(_ASSET_CACHE["assets"])
    assets: dict[str, dict[str, Any]] = {}
    try:
        req = urllib.request.Request(
            f"https://api.github.com/repos/{GITHUB_REPO}/releases/tags/{PACK_RELEASE_TAG}",
            headers={"Accept": "application/vnd.github+json", "User-Agent": "Morkyn-Packs"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        for asset in payload.get("assets") or []:
            if isinstance(asset, dict) and asset.get("name"):
                assets[str(asset["name"])] = {"url": asset.get("browser_download_url"), "size": int(asset.get("size") or 0)}
    except Exception:
        assets = {}
    with _LOCK:
        if assets:
            _ASSET_CACHE.update({"at": time.time(), "assets": assets})
    return assets


# --- status -----------------------------------------------------------------

def status(check_online: bool = False) -> dict[str, Any]:
    """The hardware, the choice, the catalog for this platform with what is installed and fetchable, and whether llama_cpp loads."""
    have = {p["id"]: p for p in installed()}
    assets = available_assets() if check_online else dict(_ASSET_CACHE["assets"])
    packs = []
    for entry in catalog_here():
        name = asset_name(entry["id"])
        packs.append({
            **entry,
            "asset": name,
            "installed": have.get(entry["id"]),
            "available": assets.get(name),
            "progress": _PROGRESS.get(entry["id"]),
        })
    try:
        from app.hardware import summary

        hardware = summary()
    except Exception as exc:
        hardware = {"gpus": [], "recommended": "llama-cpp-cpu", "why": f"detection failed: {exc}"}
    return {
        "platform": {"os": os_tag(), "arch": arch_tag(), "python": python_tag()},
        "runtime_dir": str(packs_dir()),
        "packaged": bool(getattr(sys, "frozen", False)),
        "llama_cpp": provides("llama_cpp"),
        "hardware": hardware,
        "choice": choice(),
        "release": f"https://github.com/{GITHUB_REPO}/releases/tag/{PACK_RELEASE_TAG}",
        "packs": packs,
    }


# --- install / remove -------------------------------------------------------

def _set_progress(pack_id: str, **fields: Any) -> None:
    with _LOCK:
        entry = _PROGRESS.setdefault(pack_id, {})
        entry.update(fields)
        entry["at"] = time.time()


def download(url: str, dest: Path, pack_id: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "Morkyn-Packs"})
    with urllib.request.urlopen(req, timeout=60) as resp, dest.open("wb") as fh:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            fh.write(chunk)
            done += len(chunk)
            _set_progress(pack_id, state="downloading", bytes=done, total=total)


def _unpack(zip_path: Path, target: Path) -> dict[str, Any]:
    tmp = target.with_name(target.name + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        if "pack.json" not in names or not any(n.startswith("site/") for n in names):
            raise ValueError("not a Mørkyn runtime pack (pack.json and site/ expected)")
        zf.extractall(tmp)
        if os.name != "nt":
            # extractall drops the mode bits; a pack's helper programs (Qt's
            # QtWebEngineProcess) then fail with "failed to execvp".
            for info in zf.infolist():
                mode = (info.external_attr >> 16) & 0o777
                if mode and not info.is_dir():
                    (tmp / info.filename).chmod(mode)
    meta = _read_json(tmp / "pack.json")
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    tmp.rename(target)
    return meta


def install(pack_id: str, url: str | None = None, *, wait: bool = False) -> dict[str, Any]:
    """Download and unpack a pack (in a thread unless ``wait``). Progress is read from status()."""
    entry = next((e for e in CATALOG if e["id"] == pack_id), None)
    if entry is None:
        return {"ok": False, "error": f"unknown pack {pack_id!r}"}
    if os_tag() not in entry["os"]:
        return {"ok": False, "error": f"{pack_id} is not built for {os_tag()}"}
    if url is None:
        asset = available_assets(force=True).get(asset_name(pack_id))
        url = str((asset or {}).get("url") or "")
    if not url:
        return {"ok": False, "error": f"no {asset_name(pack_id)} on the {PACK_RELEASE_TAG} release yet"}
    current = _PROGRESS.get(pack_id) or {}
    if current.get("state") in {"downloading", "unpacking"}:
        return {"ok": True, "already": True}

    def work() -> None:
        try:
            _set_progress(pack_id, state="downloading", bytes=0, total=0, error="")
            downloads = packs_dir() / ".downloads"
            zip_path = downloads / asset_name(pack_id)
            download(url, zip_path, pack_id)
            _set_progress(pack_id, state="unpacking")
            meta = _unpack(zip_path, packs_dir() / pack_id)
            meta = {**meta, "id": pack_id, "installed_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
            meta.setdefault("python_tag", python_tag())
            meta.setdefault("os", os_tag())
            meta.setdefault("arch", arch_tag())
            (packs_dir() / pack_id / "pack.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
            try:
                zip_path.unlink()
            except Exception:
                pass
            activate()
            _set_progress(pack_id, state="installed")
        except Exception as exc:
            _set_progress(pack_id, state="failed", error=f"{exc.__class__.__name__}: {exc}"[:300])

    if wait:
        work()
        return {"ok": _PROGRESS.get(pack_id, {}).get("state") == "installed", **(_PROGRESS.get(pack_id) or {})}
    threading.Thread(target=work, daemon=True, name=f"pack-{pack_id}").start()
    return {"ok": True, "started": True}


def remove(pack_id: str) -> dict[str, Any]:
    folder = packs_dir() / pack_id
    if not folder.is_dir():
        return {"ok": False, "error": "not installed"}
    site = str(folder / "site")
    if site in sys.path:
        sys.path.remove(site)
    shutil.rmtree(folder, ignore_errors=True)
    _PROGRESS.pop(pack_id, None)
    return {"ok": True, "note": "Restart Mørkyn to unload the engine."}


def auto_install_window_if_needed() -> dict[str, Any]:
    """A packaged Linux start that wants the window but cannot import pywebview: fetch the window pack.

    This start opens the browser; the next one opens the window.
    """
    if not getattr(sys, "frozen", False) or os_tag() != "linux" or os.getenv("MORKYN_NO_AUTO_PACK"):
        return {"ok": True, "skipped": "not a packaged Linux build"}
    if provides("webview"):
        return {"ok": True, "skipped": "not needed"}
    if any(p["id"] == "qt-window" and p.get("fits") for p in installed()):
        return {"ok": True, "skipped": "installed"}
    return install("qt-window")


def auto_install_if_needed() -> dict[str, Any]:
    """At a packaged start with the engine on auto and nothing providing llama_cpp, fetch the fitting pack.

    Only a packaged build (a checkout has pip), only once per start, and never
    when a download is already running or the pack is installed.
    """
    if not getattr(sys, "frozen", False) or os.getenv("MORKYN_NO_AUTO_PACK"):
        return {"ok": True, "skipped": "not packaged"}
    picked = choice()
    if picked["mode"] != "auto" or provides("llama_cpp"):
        return {"ok": True, "skipped": "not needed"}
    pack_id = picked["pack"]
    if any(p["id"] == pack_id and p.get("fits") for p in installed()):
        return {"ok": True, "skipped": "installed"}
    return install(pack_id)
