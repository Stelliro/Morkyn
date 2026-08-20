"""Run the bare-assert test files that `unittest` cannot see on its own.

Most files in tests/ are written as plain ``def test_*(): assert ...`` functions
with no ``TestCase``. ``unittest discover`` collects **zero** tests from them, so
they pass vacuously and rot silently -- 127 real checks were invisible until this
wrapper made them run. pytest would collect them, but pytest is not installed in
this environment, and those files never isolate their runtime paths either, so
running them under pytest would write fixtures into the player's real
``data/world.db``.

This module imports each of them under isolated ``AI_RPG_*`` paths and wraps every
zero-argument ``test_*`` function in a generated ``TestCase``, so they run in the
normal suite and a regression fails loudly.

Deleting this file silently drops that coverage. Convert a file to real
``TestCase`` classes and it is skipped here automatically.
"""
from __future__ import annotations

import importlib
import inspect
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-bare-test-"))
_ENV = {
    "AI_RPG_DB": str(_TMP / "world.db"),
    "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
    "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
    "AI_RPG_CONSOLIDATED_FACTS": str(_TMP / "facts.jsonl"),
    "AI_RPG_CAMPAIGN_SLOTS": str(_TMP / "slots"),
    "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
    "AI_RPG_PACK_DIR": str(_TMP / "packs"),
    "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
    "AI_RPG_IDEA_BANK": str(_TMP / "idea_bank"),
    "AI_RPG_LAUNCHER_PREFS": str(_TMP / "launcher_prefs.json"),
}
os.environ.update(_ENV)

from app.db import db_path, init_db  # noqa: E402
import app.world as _world  # noqa: E402

# Files that already define real TestCase classes; unittest finds those itself.
_NATIVE_UNITTEST = {
    "test_bare_assert_files",
    "test_continuity",
    "test_dice_and_packs",
    "test_player_resources",
    "test_setup_quality",
    "test_venues",
}


def _assert_isolated() -> None:
    for label, value in (
        ("AI_RPG_DB", db_path()),
        ("AI_RPG_SOURCE_INDEX", _world.source_index_dir()),
        ("AI_RPG_MODEL_TRACE_DIR", _world.model_trace_dir()),
    ):
        if not str(value).startswith(str(_TMP)):
            raise AssertionError(
                f"test isolation failed: {label} resolves to {value!r}, "
                f"outside the temp dir {str(_TMP)!r}"
            )


def setUpModule() -> None:
    """Re-pin runtime paths: unittest imports every module before running any test."""
    os.environ.update(_ENV)
    _assert_isolated()


_assert_isolated()
init_db()


def _make_case(module_name: str, functions: list[tuple[str, object]]) -> type[unittest.TestCase]:
    body: dict[str, object] = {"__doc__": f"Bare-assert checks from tests/{module_name}.py"}

    def _setup(self) -> None:  # noqa: ANN001
        os.environ.update(_ENV)

    body["setUp"] = _setup
    for name, fn in functions:
        def method(self, _fn=fn) -> None:  # noqa: ANN001
            _fn()

        method.__name__ = name
        method.__doc__ = (getattr(fn, "__doc__", "") or "").strip().split("\n")[0]
        body[name] = method
    return type(f"Bare_{module_name}", (unittest.TestCase,), body)


def _collect() -> None:
    for path in sorted((ROOT / "tests").glob("test_*.py")):
        module_name = path.stem
        if module_name in _NATIVE_UNITTEST:
            continue
        module = importlib.import_module(module_name)
        functions = [
            (name, obj)
            for name, obj in vars(module).items()
            if name.startswith("test_")
            and inspect.isfunction(obj)
            and obj.__module__ == module_name
            and not inspect.signature(obj).parameters
        ]
        if not functions:
            continue
        globals()[f"Bare_{module_name}"] = _make_case(module_name, functions)


_collect()

if __name__ == "__main__":
    unittest.main(verbosity=2)
