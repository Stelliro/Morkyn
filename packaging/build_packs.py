"""Build a runtime pack: llama-cpp-python for one accelerator, zipped for app/runtime_packs.py.

    python packaging/build_packs.py cuda|cpu|metal|vulkan [--out dist/packs] [--python-tag cp312]

The pack is built for the interpreter that runs this script (its Python tag is
the pack's), on this OS and architecture. Each accelerator installs
``llama-cpp-python[server]==<pin>`` into a temporary site folder from the
matching wheel index (Vulkan builds from source with CMAKE_ARGS), drops the
packages the app build already carries, writes ``pack.json`` and zips
``pack.json`` + ``site/`` as ``morkyn-pack-llama-cpp-<acc>-<os>-<arch>-<pytag>.zip``.
The GitHub workflow attaches these to the ``runtime-packs`` release.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PIN = "0.3.22"
INDEX = {
    "cuda": "https://abetlen.github.io/llama-cpp-python/whl/cu124",
    "cpu": "https://abetlen.github.io/llama-cpp-python/whl/cpu",
    "metal": "https://abetlen.github.io/llama-cpp-python/whl/metal",
    "vulkan": "",  # built from source: CMAKE_ARGS=-DGGML_VULKAN=on, needs the Vulkan SDK
}
# Packages the app build already ships; a pack keeps only what it adds.
SHIPPED = {
    "numpy", "numpy.libs", "pydantic", "pydantic_core", "fastapi", "starlette", "uvicorn", "anyio", "sniffio", "idna",
    "h11", "click", "typing_extensions", "annotated_types", "typing_inspection", "PIL", "pillow.libs", "bin",
}


def os_tag() -> str:
    return {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")


def arch_tag() -> str:
    machine = platform.machine().lower()
    if machine in {"x86_64", "amd64", "x64"}:
        return "x64"
    if machine in {"arm64", "aarch64"}:
        return "arm64"
    return machine


def python_tag() -> str:
    return f"cp{sys.version_info[0]}{sys.version_info[1]}"


# Add-on packs (app/runtime_packs.CATALOG kind "addon"): the local speech engine
# for the packaged app, which has no pip (Stell, 2026-10-22), and the Linux
# window, pywebview on Qt WebEngine (2026-10-23; Linux only). The window is on
# PySide6 (LGPL), not PyQt6 (GPL-3.0): the packs are published and the game
# imports them into its own process (Stell, 2026-10-23: no GPL in the packs).
ADDONS = {"piper": ("piper-speech", "piper-tts==1.8.0"), "window": ("qt-window", "pywebview[pyside6]==6.2.1")}


def build(acc: str, out_dir: Path) -> Path:
    if acc not in INDEX and acc not in ADDONS:
        raise SystemExit(f"unknown pack {acc!r}; one of {', '.join([*INDEX, *ADDONS])}")
    pack_id, requirement = ADDONS[acc] if acc in ADDONS else (f"llama-cpp-{acc}", f"llama-cpp-python[server]=={PIN}")
    name = f"morkyn-pack-{pack_id}-{os_tag()}-{arch_tag()}-{python_tag()}.zip"
    work = Path(tempfile.mkdtemp(prefix="morkyn-pack-"))
    site = work / "site"
    cmd = [sys.executable, "-m", "pip", "install", "--target", str(site), "--upgrade", requirement]
    if acc == "cuda" and os_tag() == "linux":
        # The Linux CUDA wheel links the CUDA runtime and cuBLAS without carrying
        # them; a desktop with only the driver has neither (app/runtime_packs._preload_cuda).
        cmd += ["nvidia-cuda-runtime-cu12==12.4.*", "nvidia-cublas-cu12==12.4.*"]
    env = dict(os.environ)
    if acc in ADDONS:
        cmd += ["--prefer-binary"]
    elif INDEX[acc]:
        cmd += ["--extra-index-url", INDEX[acc]]
    else:
        cmd += ["--no-binary", "llama-cpp-python"]
        env["CMAKE_ARGS"] = env.get("CMAKE_ARGS") or "-DGGML_VULKAN=on"
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True, env=env)
    for entry in list(site.iterdir()):
        stem = entry.name.split("-")[0] if entry.name.endswith(".dist-info") else entry.name
        if stem in SHIPPED or entry.name in SHIPPED:
            shutil.rmtree(entry, ignore_errors=True) if entry.is_dir() else entry.unlink()
    meta = {
        "id": pack_id,
        "version": requirement.split("==")[-1],
        "accelerator": "" if acc in ADDONS else acc,
        "python_tag": python_tag(),
        "os": os_tag(),
        "arch": arch_tag(),
        "built": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "index": "pypi" if acc in ADDONS else (INDEX[acc] or "source"),
    }
    (work / "pack.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / name
    if target.exists():
        target.unlink()
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        zf.write(work / "pack.json", "pack.json")
        for path in sorted(site.rglob("*")):
            if path.is_file():
                zf.write(path, "site/" + path.relative_to(site).as_posix())
    shutil.rmtree(work, ignore_errors=True)
    print(f"pack: {target} ({target.stat().st_size // (1 << 20)} MB)")
    return target


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("accelerator", choices=sorted([*INDEX, *ADDONS]))
    ap.add_argument("--out", default=str(ROOT / "dist" / "packs"))
    args = ap.parse_args(argv)
    build(args.accelerator, Path(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
