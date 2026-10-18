# Packaging: the exe and the Linux/macOS builds

Stell (2026-10-18, after 0.10.0-dev.14): "we should probably leave a release here and start
working on an exe and linux/mac equivalent." This is how the packaged build is made and what
it is made of.

## What a build is

One folder per platform, built with PyInstaller from the real entry point, `morkyn_app.py`
(the window, the launcher and the servers in one process tree):

```
Morkyn/
  Morkyn.exe            Windows (Morkyn.app on macOS, ./Morkyn on Linux)
  _internal/            Python, app/, the libraries (uvicorn, fastapi, llama-cpp-python, pywebview)
  static/ content/ config/ Media/    the game's files, copied beside the exe
  data/                 saves, prefs, logs, portraits, voices, models: made on first run, never inside the bundle
  README-package.md
```

Nothing in the game's code knows it is packaged except two places:

- `app/paths.py`: `ROOT` is the repo root from a checkout and the folder beside the executable
  when frozen. Every module that used `Path(__file__).resolve().parent.parent` takes `ROOT`
  from here (tests/test_packaging_paths.py keeps it so), so `ROOT / "data"`, `ROOT / "static"`
  and the rest resolve the same way in both worlds.
- `app/launcher.py` and `morkyn_app.py`: a packaged build has no interpreter to run `-m uvicorn`,
  `-m llama_cpp.server`, `-m app.model_limits` or `-c ...`. The launcher asks the exe instead:
  `Morkyn.exe --serve host port`, `--run-module name args`, `--run-code "..."`
  (`server_command`, `module_command`, `snippet_command`), and `morkyn_app.main` dispatches them.

The local model is not in the build. It is a `.gguf` the player points the Model settings at,
or a cloud API. `llama-cpp-python` is inside (CUDA wheels on Windows, CPU wheels elsewhere);
`data/mle-models` beside the exe is where the in-app downloader puts weights.

## Runtime packs and versions (Stell, 2026-10-19)

"could we make the exe seperate from its dependancies so we dont ship them together? also, we
will need a new method for updating, but we should probbaly make it so the user can select a
version, this is a future proofing method i want to use" and "we need hardware specific auto
installs as well as an area the user can select what they want and if they want to use a custom
one".

The home folder (beside the executable the player downloaded) holds three shared things:

```
Morkyn/                     the home (app.paths.ROOT)
  Morkyn.exe + _internal/   the build the player downloaded (about 60 MB)
  static/ content/ config/ Media/
  data/                     saves, prefs, logs, models (shared by every version)
  runtime/<pack>/           engine packs: llama-cpp-python per accelerator (shared)
  versions/<tag>/Morkyn/    other installed versions, each a full app build
```

- **Packs** (`app/runtime_packs.py`): the app build does not ship llama-cpp-python. A pack is a
  zip (`pack.json` + `site/`) per accelerator, OS, architecture and Python tag, built by
  `packaging/build_packs.py` and attached to the standing `runtime-packs` release. `activate()`
  runs in every process of the app and puts the chosen engine on `sys.path`. The choice is the
  launcher pref `engine_pack`: `auto` (the pack that fits the hardware, `app/hardware.py`:
  CUDA for NVIDIA, Metal on Apple Silicon, Vulkan for AMD and Intel, else CPU; installed on
  its own at the first packaged start that needs it), a pack id, `custom` (a folder or zip of
  the player's own build, `engine_pack_custom`) or `none`. Catalog: `llama-cpp-cuda`
  (Windows, Linux), `llama-cpp-metal` (macOS), `llama-cpp-vulkan` (Windows, Linux; built from
  source, not on the release yet), `llama-cpp-cpu` (all).
- **Versions** (`app/versions.py`): the Versions & engine panel lists the GitHub releases; the
  player installs any one (newer or older) into `versions/<tag>/` and chooses it; at the next
  start the home executable hands over to that version's executable with `MORKYN_HOME` set, so
  every version shares `data/` and the packs. "Use this build" clears the choice. A chosen
  version that dies within seconds is dropped, so a bad download never locks the player out.
- Routes: `/api/versions` (+`/install`, `/activate`, `/remove`), `/api/runtime/packs`
  (+`/install`, `/remove`), `/api/runtime/engine`. The panel is the Updates modal of a packaged
  build (static/app.js, `renderVersionsList`, `renderEnginePanel`).
- Paths: `app.paths.ROOT` is the home (`MORKYN_HOME`, else beside the exe, else the repo) for
  `data/`, `runtime/`, `versions/`; `app.paths.APP_DIR` is the running version's own files
  (`static/`, `content/`, `config/`, `Media/`).

### Slim build verified (2026-10-19)

The Windows app build without llama-cpp-python: 53 MB zip (was 793 MB). The CUDA pack built
with `packaging/build_packs.py cuda` is 219 MB zipped, 837 MB installed in `runtime/`.
Installed into the slim build's `runtime/` through `runtime_packs.install`, then from the exe:
`import llama_cpp` loads from the pack and finds the RTX 4070 Ti (GPU offload true), and
`Morkyn.exe --run-module llama_cpp.server --help` runs the managed server from the pack.
Two classes found and fixed on the way, both in the spec: the app build ships the whole
standard library (a pack's `import pickletools` failed), and the packages the app shares
with packs ship whole (`fastapi.middleware.cors` was missing for the server).
The version handover was verified the same way: with `data/active_version.json` naming an
installed `versions/0.10.0-dev.15/`, the home exe started that build, which served its own
`static/` while writing to the home's `data/`.

## Building

- Windows: `powershell -ExecutionPolicy Bypass -File packaging\build.ps1` (add `-Console` for a
  build that keeps a console window). Result: `dist\Morkyn\` and
  `dist\Morkyn-<version>-windows-x64.zip`.
- Linux/macOS: `bash packaging/build.sh` (add `--console`). Result: `dist/Morkyn/` or
  `dist/Morkyn.app`, and a `.tar.gz` / `.zip`.
- Both need the repo's requirements plus `pyinstaller sse-starlette starlette-context
  pydantic-settings` (the llama.cpp server extras; the scripts install them).
- The spec is `packaging/morkyn.spec`: hidden imports for uvicorn's lazily imported workers,
  `app.main` (imported by name by uvicorn), the llama.cpp server and its extras, pywebview's
  platform backends; `app/comfy_workflows` and llama-cpp's binaries as data; tests, tools and
  tkinter excluded. The icon is made from `Media/morkyn-logo.png` at build time.

CI: `.github/workflows/package.yml` builds all three on every `v*` tag (and on request) and
attaches the archives to that tag's release. Linux and macOS install `llama-cpp-python` from the
CPU wheel index; macOS adds pywebview for the native window; Linux ships browser mode (the native
window needs PyGObject and WebKit2GTK from the distribution).

## Platform notes

- Windows: pywebview uses WebView2 (in Windows 11; Windows 10 may need the Evergreen runtime).
  The native title bar colouring (`morkyn_app.paint_frame`) is Windows-only and skipped elsewhere.
- Linux: `app/launcher.py` already ties child servers to the parent with `PR_SET_PDEATHSIG`; the
  job-object limits are Windows-only. Without pywebview the build runs `--browser` (the entry
  already falls back when `import webview` fails).
- macOS: pywebview's cocoa backend; the `.app` bundle is produced by the spec's `BUNDLE`. Code
  signing and notarisation are not set up; Gatekeeper will ask to allow the app on first open.

## First Windows build (2026-10-18)

`packaging/build.ps1 -Console` on Python 3.14 / PyInstaller 6.22: 1.6 GB folder, 793 MB zip,
of which `_internal/llama_cpp` is 784 MB (the CUDA 12.4 wheel and its cuBLAS libraries); the
rest of the app is about 60 MB. Smoke test, all from `dist\Morkyn\Morkyn.exe`:

- `--run-code` and `--run-module app.model_limits --context` answer (the frozen launcher's
  module and snippet commands work).
- `--serve 127.0.0.1 8765`: the page, `/static/app.js`, `/api/model-status` and `/api/state`
  answer 200; `data/world.db` and `data/campaign_slots` appear beside the exe, not in the repo.
- `--console` with `window_mode none`: the supervisor starts the `--serve` child and
  `/api/launcher/status` reports it supervised.
- The window (pywebview, WebView2) with `MORKYN_REMOTE_DEBUG_PORT`: the boot page hands over to
  the real main menu (Start new game, Continue, Load, Settings, Where / Engine / Pipeline).

Size is the open question: a CPU-only llama-cpp wheel would make the zip about 70 MB, but the
8B model needs the GPU. Options: ship the CUDA build as is; two Windows builds (cpu / cuda);
or download the llama-cpp wheel on first use into `data/`. Stell's call.

## First Linux build (2026-10-18, Alpine WSL, musl, Python 3.12)

`packaging/build.sh` from a clean `git archive` of HEAD in `/tmp`, without llama-cpp-python
(no musl wheel; the spec builds without it) and without pywebview: 126 MB folder, 57 MB tarball.
`./Morkyn --run-code`, `--run-module app.model_limits --context` and `--serve` all work; the
page, `/static/app.js`, `/api/model-status` and `/api/state` answer; `data/` lands beside the
binary. PyInstaller's dependency scan prints "Error loading shared library libgcc_s..." for the
manylinux wheels' bundled libraries on musl; the build still runs. A glibc build (CI's
ubuntu-22.04) is the one to ship; the Alpine run proves the layout.

The in-game updater in a packaged build says so and compares the running version to the
newest GitHub release instead of offering a git pull (`app/updates.py`, the Updates panel).

## Still to do

- Smoke test the rest from the exe: new game on a cloud API and on a local GGUF, pop-outs,
  `--browser`, `lan`.
- A glibc Linux build and the macOS build, via the workflow on the next tag.
- A smaller build: drop the CUDA llama-cpp wheel from the Windows package in favour of a
  download on first use, if the zip is too large for itch.
