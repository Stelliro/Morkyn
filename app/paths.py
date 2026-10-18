"""Where Mørkyn's folders live.

From a checkout, the repo root: ``static/``, ``content/``, ``config/``, ``Media/``
and the writable ``data/`` sit beside ``app/``. From a packaged build (PyInstaller,
``sys.frozen``), the same folders sit beside the executable, and the Python code
is unpacked elsewhere (``_internal/``); ``Path(__file__)`` would point into that
unpack, so every module takes its root from here instead (packaging, 2026-10-18).
"""
from __future__ import annotations

import sys
from pathlib import Path


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


ROOT = app_root()
