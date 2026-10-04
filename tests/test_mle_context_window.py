"""The budget follows the context the MLE actually loaded, and its overflow is a context error.

After the loader fell back to 8,192 tokens, `context_window_tokens()` still
returned the env value (32,768): the full contract was chosen, nothing was
pruned, and every turn overflowed llama_cpp. That overflow text ("Requested
tokens (N) exceed context window of M") was not recognised as a context
error either, so the draft was repeated unchanged as `draft_retry` instead of
`draft_compact_retry`.

Run:  python -m unittest tests.test_mle_context_window
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-mle-ctx-test-"))
_ENV = {
    "AI_RPG_DB": str(_TMP / "world.db"),
    "AI_RPG_PACK_DIR": str(_TMP / "packs"),
    "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
    "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
    "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
    "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
    "AI_RPG_CAMPAIGN_SLOTS": str(_TMP / "slots"),
}
os.environ.update(_ENV)

from app import db, llm, mle  # noqa: E402
from app.prompts import COMPACT_SYSTEM_PROMPT, SYSTEM_PROMPT  # noqa: E402


def setUpModule():
    os.environ.update(_ENV)
    assert str(db.db_path()).startswith(str(_TMP)), db.db_path()
    db.init_db()


_MLE_OVERFLOW = (
    "MLE generation failed (qwen2.5-7b-instruct-q4_k_m.gguf). "
    "Requested tokens (9400) exceed context window of 8192"
)


def _loaded_at(n_ctx: int):
    return (
        mock.patch.dict(os.environ, {"AI_RPG_CONTEXT_TOKENS": "32768"}),
        mock.patch.object(mle, "_MODEL", object()),
        mock.patch.object(mle, "_MODEL_CTX", n_ctx),
    )


class TestWindowFollowsTheLoadedContext(unittest.TestCase):
    def test_loaded_context_reports_zero_without_a_model(self):
        with mock.patch.object(mle, "_MODEL", None), mock.patch.object(mle, "_MODEL_CTX", 8192):
            self.assertEqual(mle.loaded_context(), 0)

    def test_window_is_the_loaded_context_when_smaller(self):
        a, b, c = _loaded_at(8192)
        with a, b, c:
            self.assertEqual(llm.context_window_tokens({"provider": "mle"}), 8192)
            # Other providers keep the env value.
            self.assertEqual(llm.context_window_tokens({"provider": "ollama"}), 32768)

    def test_window_is_the_env_value_before_a_load(self):
        with mock.patch.dict(os.environ, {"AI_RPG_CONTEXT_TOKENS": "32768"}), mock.patch.object(mle, "_MODEL", None):
            self.assertEqual(llm.context_window_tokens({"provider": "mle"}), 32768)

    def test_compact_contract_is_chosen_at_the_fallback_context(self):
        a, b, c = _loaded_at(8192)
        with a, b, c:
            system_prompt, _verify, degraded = llm.fitting_system_prompts({"provider": "mle"})
        self.assertEqual(system_prompt, COMPACT_SYSTEM_PROMPT)
        self.assertTrue(degraded)

    def test_budget_prunes_for_the_fallback_context(self):
        a, b, c = _loaded_at(8192)
        with a, b, c, mock.patch.object(llm, "get_model_config", return_value={"provider": "mle"}):
            _system, _user, diagnostics = llm.enforce_token_budget(COMPACT_SYSTEM_PROMPT, "{}")
            # The full contract cannot fit the fallback context, and the budget
            # now says so instead of letting llama_cpp find out.
            with self.assertRaises(llm.LlmError) as caught:
                llm.enforce_token_budget(SYSTEM_PROMPT, "{}")
        self.assertEqual(diagnostics.get("context_window"), 8192)
        self.assertIn("context_window=8192", str(caught.exception))


class TestMleOverflowIsAContextError(unittest.TestCase):
    def test_markers(self):
        self.assertTrue(llm._is_context_length_error(llm.LlmError(_MLE_OVERFLOW)))
        self.assertTrue(llm._is_context_length_error(llm.LlmError("the request exceeds the available context size")))
        self.assertFalse(llm._is_context_length_error(llm.LlmError("stop")))

    def test_overflowing_draft_is_retried_compact_not_repeated(self):
        phases: list[str] = []
        scene = " ".join(["You watch the rain cross the yard and wait."] * 30)

        def fake_json(*_args, **kwargs):
            phase = kwargs.get("phase")
            phases.append(phase)
            if phase == "draft":
                raise llm.LlmError(_MLE_OVERFLOW)
            return {
                "scene_plan": {"goal": "look", "focus_points": [{"kind": "scene", "summary": "yard"}]},
                "narration_segments": [{"label": "scene", "text": scene}],
                "player": {},
                "self_check": {"passed": True, "issues_found": [], "corrections_made": []},
                "turn_summary": "looked",
                "scene_focus": "action",
            }

        with mock.patch.object(llm, "_chat_json", side_effect=fake_json), mock.patch.object(
            llm, "_chat_text", return_value=""
        ), mock.patch.object(llm, "draft_mode_enabled", return_value=False):
            result = llm.generate_turn({"player": {"name": "Ash"}, "turn_plan": {"turn_kind": "player_action"}}, "I look around")
        self.assertIn("draft_compact_retry", phases)
        self.assertNotIn("draft_retry", phases, "an overflow must not be re-sent unchanged")
        usage_phases = [entry.get("phase") for entry in result.get("_model_usage") or []]
        self.assertNotIn("draft_retry", usage_phases)
        self.assertTrue(str(result.get("narration") or "").startswith("You watch"))


if __name__ == "__main__":
    unittest.main()
