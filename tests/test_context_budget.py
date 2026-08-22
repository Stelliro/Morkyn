"""Regression tests: the default configuration must actually reach the model.

A default launch resolved `context_window=8192` while `SYSTEM_PROMPT` alone
estimates ~9100 tokens. `enforce_token_budget` raised

    Token budget exceeded: system prompt alone is ~9894 tokens for context_window=8192

on turn one, the turn fell back to deterministic prose, and the player got flat
canned narration on *every* turn with nothing on screen explaining why. The
playtest tools in `tools/` all export `OLLAMA_CONTEXT_TOKENS=32768`, so no test
or probe ever exercised the shipped default.

Two guarantees here:
  1. the default context window fits the full system contract, and
  2. a smaller window degrades to the compact contract instead of hard-failing.

Run:  python -m unittest tests.test_context_budget
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-ctx-test-"))
_ENV = {
    "AI_RPG_DB": str(_TMP / "world.db"),
    "AI_RPG_PACK_DIR": str(_TMP / "packs"),
    "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
    "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
    "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
    "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
}
os.environ.update(_ENV)

import app.llm as llm  # noqa: E402
from app.db import db_path  # noqa: E402
from app.launcher_prefs import default_prefs  # noqa: E402
from app.prompts import COMPACT_SYSTEM_PROMPT, SYSTEM_PROMPT  # noqa: E402


def _assert_isolated() -> None:
    if not str(db_path()).startswith(str(_TMP)):
        raise AssertionError(f"test isolation failed: AI_RPG_DB resolves to {db_path()!r}")


def setUpModule() -> None:
    """Re-pin paths: unittest imports every test module before running any test."""
    os.environ.update(_ENV)
    _assert_isolated()


_assert_isolated()


class TestDefaultContextFitsContract(unittest.TestCase):
    """The shipped defaults, with no env overrides, must run a real turn."""

    def setUp(self):
        self._saved = {
            key: os.environ.pop(key, None)
            for key in ("OLLAMA_CONTEXT_TOKENS", "AI_RPG_LLAMA_CPP_CONTEXT")
        }

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_default_window_holds_system_prompt_plus_working_room(self):
        window = llm.context_window_tokens({"provider": "ollama"})
        needed = llm.estimated_tokens(SYSTEM_PROMPT) + llm.MIN_TURN_HEADROOM_TOKENS
        self.assertGreaterEqual(
            window,
            needed,
            f"default context window {window} cannot hold the system contract "
            f"(~{llm.estimated_tokens(SYSTEM_PROMPT)} tokens) plus turn headroom",
        )

    def test_default_launcher_pref_matches(self):
        pref = int(default_prefs()["llama_cpp_context"])
        needed = llm.estimated_tokens(SYSTEM_PROMPT) + llm.MIN_TURN_HEADROOM_TOKENS
        self.assertGreaterEqual(pref, needed, "launcher default context is too small to play")

    def test_default_config_selects_the_full_contract(self):
        system, _verify, degraded = llm.fitting_system_prompts({"provider": "ollama"})
        self.assertIs(system, SYSTEM_PROMPT)
        self.assertFalse(degraded)

    def test_budget_guard_does_not_raise_on_defaults(self):
        system, _verify, _degraded = llm.fitting_system_prompts({"provider": "ollama"})
        # Should return a usable pair, not raise LlmError.
        got_system, got_user, diag = llm.enforce_token_budget(system, "world packet " * 200)
        self.assertTrue(got_system)
        self.assertTrue(got_user)
        self.assertTrue(diag.get("enabled"))


class TestSmallWindowDegradesInsteadOfFailing(unittest.TestCase):
    """A player who lowers the context must still get model narration."""

    def test_small_windows_pick_the_compact_contract(self):
        for window in (4096, 8192):
            with self.subTest(window=window):
                system, verify, degraded = llm.fitting_system_prompts(
                    {"provider": "ollama", "context_window": window}
                )
                self.assertIs(system, COMPACT_SYSTEM_PROMPT)
                self.assertTrue(verify)
                self.assertTrue(degraded)

    def test_compact_contract_actually_fits_a_small_window(self):
        for window in (4096, 8192):
            with self.subTest(window=window):
                system, _verify, _degraded = llm.fitting_system_prompts(
                    {"provider": "ollama", "context_window": window}
                )
                self.assertLess(
                    llm.estimated_tokens(system),
                    window - 128,
                    "compact contract still overflows, enforce_token_budget would raise",
                )

    def test_small_window_no_longer_hard_fails(self):
        system, _verify, _degraded = llm.fitting_system_prompts(
            {"provider": "ollama", "context_window": 8192}
        )
        try:
            llm.enforce_token_budget(system, "world packet " * 200)
        except llm.LlmError as exc:  # pragma: no cover - the bug being fixed
            self.fail(f"small context window still kills the turn: {exc}")

    def test_full_contract_still_wins_when_there_is_room(self):
        system, _verify, degraded = llm.fitting_system_prompts(
            {"provider": "ollama", "context_window": 32768}
        )
        self.assertIs(system, SYSTEM_PROMPT)
        self.assertFalse(degraded)

    def test_llama_cpp_keeps_its_compact_contract(self):
        system, verify, degraded = llm.fitting_system_prompts(
            {"provider": "llama_cpp", "context_window": 32768}
        )
        self.assertIs(system, COMPACT_SYSTEM_PROMPT)
        self.assertTrue(verify)
        self.assertFalse(degraded, "llama_cpp uses the compact contract by design, not by degradation")


if __name__ == "__main__":
    unittest.main()
