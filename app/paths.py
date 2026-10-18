"""Where Mørkyn's folders live.

Two roots (packaging, 2026-10-18/19):

- ``ROOT`` is the home: the writable, shared folders (``data/``, ``runtime/`` with the
  downloaded dependency packs, ``versions/`` with the installed app versions). From a
  checkout it is the repo root; from a packaged build it is the folder beside the
  executable; ``MORKYN_HOME`` overrides it, which is how a version the home executable
  hands over to keeps using the home's ``data/``.
- ``APP_DIR`` is this version's own files (``static/``, ``content/``, ``config/``,
  ``Media/``): the repo root, or the folder beside the executable that is running.

``Path(__file__)`` would point into PyInstaller's unpack, so every module takes its
roots from here (tests/test_packaging_paths.py keeps it so).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent


def app_dir() -> Path:
    """This version's files: static/, content/, config/, Media/."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return _REPO


def app_root() -> Path:
    """The home: data/, runtime/, versions/. MORKYN_HOME wins; else beside the exe; else the repo."""
    home = os.getenv("MORKYN_HOME", "").strip()
    if home:
        return Path(home).expanduser().resolve()
    return app_dir()


ROOT = app_root()
APP_DIR = app_dir()
