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

## Still to do

- First local Windows build smoke test: start, open the window, new game on a cloud API and on a
  local GGUF, pop-outs, `--browser`, `--console`, `lan`.
- Run `packaging/build.sh` on Alpine WSL (musl) and on a glibc distribution; macOS only via CI.
- The in-game updater (`app/updates.py`) is a git checkout feature; the packaged build should
  show "download the next build" instead of offering an update.
- A smaller build: drop the CUDA llama-cpp wheel from the Windows package in favour of a
  download on first use, if the zip is too large for itch.
