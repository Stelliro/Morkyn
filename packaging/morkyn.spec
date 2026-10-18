# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Mørkyn's packaged build (one folder).

    python -m PyInstaller packaging/morkyn.spec --noconfirm

Layout after packaging/build.ps1 or build.sh (the folders beside the exe are
what app/paths.py's ROOT points at; data/ is created there on first run):

    dist/Morkyn/
      Morkyn.exe (Morkyn on Linux/macOS)
      _internal/        Python, the app package and its libraries
      static/ content/ config/ Media/   copied by the build script
      data/             saves, prefs, logs, models (made on first run)

Set MORKYN_BUILD_CONSOLE=1 for a build that keeps a console window (for
diagnosing a start that shows nothing).
"""
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

ROOT = Path(SPECPATH).resolve().parent  # noqa: F821 - SPECPATH is set by PyInstaller
sys.path.insert(0, str(ROOT))

hiddenimports = [
    "app.main",  # uvicorn.run("app.main:app") imports it by name
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.http.httptools_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "llama_cpp.server.__main__",
    "sse_starlette",
    "starlette_context",
    "pydantic_settings",
    "app.model_limits",
]
hiddenimports += collect_submodules("app")

# Packages the app shares with runtime packs ship whole: packaging/build_packs.py
# leaves them out of a pack, and the llama.cpp server needs parts the game never
# imports ("fastapi.middleware.cors", 2026-10-19). Keep this list in step with
# build_packs.SHIPPED.
_shared_datas = []
for _shared in ("fastapi", "starlette", "uvicorn", "pydantic", "pydantic_core", "anyio", "sniffio", "idna", "h11",
                "click", "annotated_types", "typing_inspection", "numpy", "PIL"):
    try:
        hiddenimports += collect_submodules(_shared, filter=lambda name: ".tests" not in name and ".testing" not in name)
    except Exception as exc:
        print(f"morkyn.spec: could not collect {_shared}: {exc}")
    try:
        _shared_datas += collect_data_files(_shared)
    except Exception:
        pass

# The whole standard library: runtime packs (llama-cpp-python and its
# dependencies) are imported after the build and need modules the game never
# imports itself ("import pickletools" in diskcache failed in the first slim
# build, 2026-10-19). GUI, test and demo packages stay out.
_STDLIB_SKIP = {"tkinter", "turtle", "turtledemo", "idlelib", "test", "lib2to3", "ensurepip", "venv", "pydoc_data",
                "__phello__", "_tkinter", "antigravity", "this"}
for _name in sorted(getattr(sys, "stdlib_module_names", ())):
    if _name in _STDLIB_SKIP or _name.startswith("_test"):
        continue
    try:
        __import__(_name)
    except Exception:
        continue
    hiddenimports.append(_name)
    try:
        hiddenimports += [m for m in collect_submodules(_name) if not any(part in _STDLIB_SKIP for part in m.split("."))]
    except Exception:
        pass

datas = [
    (str(ROOT / "app" / "comfy_workflows"), "app/comfy_workflows"),
]
datas += _shared_datas
binaries = []
# The app build does not ship llama-cpp-python: it is a runtime pack (CUDA, CPU,
# Metal, Vulkan) the app downloads for the player's hardware, see
# app/runtime_packs.py and packaging/build_packs.py (Stell, 2026-10-19). Set
# MORKYN_BUNDLE_LLAMA=1 for a self-contained build. pywebview is optional too:
# a Linux build without it opens the game in the browser.
optional_packages = ["webview"]
excludes_extra: list[str] = []
if os.environ.get("MORKYN_BUNDLE_LLAMA") == "1":
    optional_packages.append("llama_cpp")
else:
    hiddenimports = [h for h in hiddenimports if not h.startswith("llama_cpp")
                     and h not in {"sse_starlette", "starlette_context", "pydantic_settings"}]
    excludes_extra = ["llama_cpp", "sse_starlette", "starlette_context", "pydantic_settings"]
for name in optional_packages:
    try:
        __import__(name)
    except Exception:
        print(f"morkyn.spec: {name} not installed; building without it")
        hiddenimports = [h for h in hiddenimports if not h.startswith(name)]
        continue
    hiddenimports += collect_submodules(name)
    datas += collect_data_files(name)
    binaries += collect_dynamic_libs(name)

icon = None
try:
    from PIL import Image

    out_dir = ROOT / "packaging" / "build"
    out_dir.mkdir(parents=True, exist_ok=True)
    logo = Image.open(ROOT / "Media" / "morkyn-logo.png").convert("RGBA")
    if sys.platform == "win32":
        icon = str(out_dir / "morkyn.ico")
        logo.save(icon, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    elif sys.platform == "darwin":
        icon = str(out_dir / "morkyn.icns")
        logo.resize((512, 512)).save(icon)
except Exception:
    icon = None

a = Analysis(  # noqa: F821
    [str(ROOT / "morkyn_app.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tests", "tools", "pytest", "tkinter", "matplotlib", "IPython", "notebook", *excludes_extra],
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Morkyn",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=os.environ.get("MORKYN_BUILD_CONSOLE") == "1",
    icon=icon,
)
coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Morkyn",
)
if sys.platform == "darwin":
    app = BUNDLE(  # noqa: F821
        coll,
        name="Morkyn.app",
        icon=icon,
        bundle_identifier="io.stelliro.morkyn",
    )
