"""A context too small for the full story contract is told to the player, not only the console.

Observed: the launcher seeded prefs with llama_cpp_context = 8192 while the
Python side's default was 32768. The server honoured 8192, llama.cpp logged
"n_ctx_seq (8192) < n_ctx_train (32768)", the compact contract ran, and the
only report was one print on the server console. No failsafe fired because
nothing failed: the model loaded at exactly the size it was asked for.

Run:  python -m unittest tests.test_context_notice
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-context-notice-"))
_ENV = {
    "AI_RPG_DB": str(_TMP / "world.db"),
    "AI_RPG_PACK_DIR": str(_TMP / "packs"),
    "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
    "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
    "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
    "AI_RPG_CAMPAIGN_SLOTS": str(_TMP / "slots"),
}
os.environ.update(_ENV)

from app import db, failsafe, llm, main  # noqa: E402


def setUpModule():
    os.environ.update(_ENV)
    assert str(db.db_path()).startswith(str(_TMP)), db.db_path()
    db.init_db()


def _with_window(tokens, provider="mle"):
    return mock.patch.dict(os.environ, {"AI_RPG_CONTEXT_TOKENS": str(tokens)}), mock.patch.object(
        llm, "get_model_config", return_value={"provider": provider}
    )


class TestTheNoticeDecision(unittest.TestCase):
    def test_a_window_below_the_contract_yields_a_notice(self):
        env, cfg = _with_window(8192)
        with env, cfg, mock.patch("app.mle.loaded_context", return_value=0):
            notice = llm.context_contract_notice()
        self.assertIsNotNone(notice)
        self.assertEqual(notice["code"], "context_below_contract")
        self.assertEqual(notice["stage"], "runtime")
        self.assertIsNone(notice["fallback"], "nothing failed, so there is nothing to accept")
        self.assertIn("8,192", notice["summary"])
        self.assertTrue(any("Gatehouse" in tip for tip in notice["tips"]))

    def test_the_default_window_yields_none(self):
        env, cfg = _with_window(32768)
        with env, cfg, mock.patch("app.mle.loaded_context", return_value=0):
            self.assertIsNone(llm.context_contract_notice())

    def test_the_loaded_context_wins_over_the_requested_one(self):
        # Requested 32768, loader fell back to 8192: that is the window the model has.
        env, cfg = _with_window(32768)
        with env, cfg, mock.patch("app.mle.loaded_context", return_value=8192):
            notice = llm.context_contract_notice()
        self.assertIsNotNone(notice)
        self.assertIn("8,192", notice["summary"])

    def test_other_providers_are_quiet(self):
        for provider in ("openai", "llama_cpp"):
            env, cfg = _with_window(8192, provider)
            with env, cfg:
                self.assertIsNone(llm.context_contract_notice(), provider)

    def test_the_threshold_matches_the_contract_switch(self):
        needed = llm.estimated_tokens(llm.SYSTEM_PROMPT) + llm.MIN_TURN_HEADROOM_TOKENS
        for window, expect_notice in ((needed - 1, True), (needed, False)):
            env, cfg = _with_window(window)
            with env, cfg, mock.patch("app.mle.loaded_context", return_value=0):
                notice = llm.context_contract_notice()
                _, _, degraded = llm.fitting_system_prompts({"provider": "mle"})
            self.assertEqual(notice is not None, expect_notice, window)
            self.assertEqual(degraded, expect_notice, "the notice and the compact switch must agree")


class TestTheRoutesCarryIt(unittest.TestCase):
    def test_llm_runtime_carries_the_notice_when_not_in_error(self):
        notice = failsafe.context_notice(8192, 11543)
        with mock.patch.object(llm, "context_contract_notice", return_value=notice), mock.patch.object(
            main, "get_llm_runtime", return_value={"phase": "ready"}
        ):
            snap = main.api_llm_runtime()
        self.assertEqual(snap.get("notice", {}).get("code"), "context_below_contract")
        self.assertNotIn("problem", snap)

    def test_an_error_phase_keeps_its_problem_and_skips_the_notice(self):
        notice = failsafe.context_notice(8192, 11543)
        with mock.patch.object(llm, "context_contract_notice", return_value=notice), mock.patch.object(
            main, "get_llm_runtime", return_value={"phase": "error", "error": "timed out"}
        ):
            snap = main.api_llm_runtime()
        self.assertIn("problem", snap)
        self.assertNotIn("notice", snap)

    def test_model_status_carries_the_notice(self):
        notice = failsafe.context_notice(8192, 11543)
        with mock.patch.object(llm, "context_contract_notice", return_value=notice), mock.patch.object(
            main, "test_model_connection", return_value={"ok": True, "provider": "mle"}
        ), mock.patch.object(main, "get_llm_runtime", return_value={"phase": "ready"}):
            status = main.api_model_status()
        self.assertEqual(status.get("notice", {}).get("code"), "context_below_contract")

    def test_a_failing_notice_never_breaks_a_status_route(self):
        with mock.patch.object(llm, "context_contract_notice", side_effect=RuntimeError("boom")), mock.patch.object(
            main, "get_llm_runtime", return_value={"phase": "ready"}
        ):
            snap = main.api_llm_runtime()
        self.assertNotIn("notice", snap)


class TestTheLaunchersAgree(unittest.TestCase):
    """The PowerShell launcher and app/launcher_prefs.py each hold a default; they drifted to 8192 vs 32768."""

    def test_both_defaults_are_the_same_and_hold_the_full_contract(self):
        ps1 = (ROOT / "Morkyn.ps1").read_text(encoding="utf-8", errors="replace")
        py = (ROOT / "app" / "launcher_prefs.py").read_text(encoding="utf-8")
        ps_default = re.search(r'llama_cpp_context\s*=\s*"?([A-Za-z0-9]+)"?', ps1).group(1).lower()
        py_default = re.search(r'"llama_cpp_context":\s*"?([A-Za-z0-9]+)"?', py).group(1).lower()
        self.assertEqual(ps_default, py_default)
        needed = llm.estimated_tokens(llm.SYSTEM_PROMPT) + llm.MIN_TURN_HEADROOM_TOKENS
        if py_default != "auto":
            self.assertGreaterEqual(int(py_default), needed)
        else:
            from app.model_limits import DEFAULT_CONTEXT_TOKENS

            self.assertGreaterEqual(DEFAULT_CONTEXT_TOKENS, needed)

    def test_the_ui_shows_a_runtime_notice(self):
        js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("data?.notice", js)
        self.assertIn("payload.notice", js)


if __name__ == "__main__":
    unittest.main()
