"""Superseded by morkyn_app.py at the repo root, which also starts the server.

Kept so old shortcuts still open the window: python tools/morkyn_window.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import morkyn_app  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(morkyn_app.main(sys.argv[1:]))
