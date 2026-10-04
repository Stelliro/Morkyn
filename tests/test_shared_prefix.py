"""One shared system prefix per turn for local models.

MLE runs llama-cpp-python in-process and the llama.cpp server is the other
local provider; both reuse their KV cache only for an identical token prefix.
A turn sent three or four unrelated system prompts (the DSL draft contract,
``VERIFY_PROMPT``, ``PROSE_REPAIR_SYSTEM_PROMPT``, and the JSON contract for
the depth fallback), so every call after the draft re-read a fresh prefix.
``system_prompt_for_phase`` gives every post-draft call on a local provider
the draft's exact system prompt as a prefix with the phase's contract after
it; the openai provider keeps its small per-task prompts because its tokens
are billed and nothing is cached. The draft call sends what it always sent.

Run:  python -m unittest tests.test_shared_prefix
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-shared-prefix-test-"))
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

from app import db, llm  # noqa: E402
from app.prompts import (  # noqa: E402
    COMPACT_SYSTEM_PROMPT,
    COMPACT_VERIFY_PROMPT,
    PROSE_REPAIR_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    VERIFY_PROMPT,
)
from app.turn_dsl import DSL_SYSTEM_PROMPT  # noqa: E402


def setUpModule():
    os.environ.update(_ENV)
    assert str(db.db_path()).startswith(str(_TMP)), db.db_path()
    db.init_db()


# Captured at import so a later test can prove the module constants never moved.
_DSL_AT_IMPORT = str(DSL_SYSTEM_PROMPT)
_SYSTEM_AT_IMPORT = str(SYSTEM_PROMPT)

MLE = {"provider": "mle", "mle_model": "qwen3:8b", "api_key": ""}
LLAMA = {"provider": "llama_cpp", "llama_cpp_base_url": "http://localhost:8080", "api_key": ""}
OPENAI = {"provider": "openai", "api_model": "cloud-model", "api_key": "k", "api_base_url": "https://example.invalid/v1"}

# A draft prompt as generate_turn builds it: the contract with a per-turn block after it.
THEME_BLOCK = "Session theme lean: keep the draft's tone."
DSL_DRAFT = f"{DSL_SYSTEM_PROMPT.rstrip()}\n\n{THEME_BLOCK}"
JSON_DRAFT = f"{SYSTEM_PROMPT.rstrip()}\n\n{THEME_BLOCK}"
PROSE_TASK = f"{PROSE_REPAIR_SYSTEM_PROMPT.rstrip()}\n\n{THEME_BLOCK}"


def _long_scene(words: int = 260) -> str:
    return " ".join(["You watch the rain cross the yard and wait."] * (words // 9))


# ---------------------------------------------------------------------------
# 1. The helper on its own
# ---------------------------------------------------------------------------
class TestLocalProvidersShareTheDraftPrefix(unittest.TestCase):
    def test_verify_starts_with_the_exact_draft_prompt(self):
        out = llm.system_prompt_for_phase(MLE, DSL_DRAFT, "verify", VERIFY_PROMPT)
        self.assertTrue(out.startswith(DSL_DRAFT))
        self.assertTrue(out.endswith(VERIFY_PROMPT))
        self.assertNotEqual(out, VERIFY_PROMPT)

    def test_prose_repair_starts_with_the_exact_draft_prompt(self):
        out = llm.system_prompt_for_phase(MLE, DSL_DRAFT, "prose_repair", PROSE_TASK)
        self.assertTrue(out.startswith(DSL_DRAFT))
        self.assertTrue(out.endswith(PROSE_REPAIR_SYSTEM_PROMPT))

    def test_the_per_turn_block_is_in_the_prefix_once_not_twice(self):
        out = llm.system_prompt_for_phase(MLE, DSL_DRAFT, "prose_repair", PROSE_TASK)
        self.assertEqual(out.count(THEME_BLOCK), 1, "the block already sits in the draft prefix")

    def test_json_depth_after_a_dsl_draft_appends_the_json_contract(self):
        out = llm.system_prompt_for_phase(MLE, DSL_DRAFT, "json_depth", SYSTEM_PROMPT)
        self.assertTrue(out.startswith(DSL_DRAFT))
        self.assertTrue(out.endswith(SYSTEM_PROMPT))

    def test_json_depth_after_a_json_draft_is_the_draft_prompt_itself(self):
        out = llm.system_prompt_for_phase(MLE, JSON_DRAFT, "json_depth", SYSTEM_PROMPT)
        self.assertEqual(out, JSON_DRAFT, "the draft already sent the JSON contract; do not send it twice")

    def test_every_phase_shares_one_identical_prefix(self):
        outs = [
            llm.system_prompt_for_phase(MLE, DSL_DRAFT, phase, task)
            for phase, task in (("verify", VERIFY_PROMPT), ("prose_repair", PROSE_TASK), ("json_depth", SYSTEM_PROMPT))
        ]
        for out in outs:
            self.assertEqual(out[: len(DSL_DRAFT)], DSL_DRAFT)

    def test_llama_cpp_gets_the_compact_contracts_after_the_prefix(self):
        verify = llm.system_prompt_for_phase(LLAMA, DSL_DRAFT, "verify", COMPACT_VERIFY_PROMPT)
        depth = llm.system_prompt_for_phase(LLAMA, DSL_DRAFT, "json_depth", COMPACT_SYSTEM_PROMPT)
        self.assertTrue(verify.startswith(DSL_DRAFT))
        self.assertTrue(verify.endswith(COMPACT_VERIFY_PROMPT))
        self.assertTrue(depth.startswith(DSL_DRAFT))
        self.assertTrue(depth.endswith(COMPACT_SYSTEM_PROMPT))

    def test_a_blank_or_retired_provider_name_counts_as_local(self):
        for provider in ("", "ollama", "MLE"):
            out = llm.system_prompt_for_phase({"provider": provider}, DSL_DRAFT, "verify", VERIFY_PROMPT)
            self.assertTrue(out.startswith(DSL_DRAFT), provider)

    def test_the_bridge_line_names_no_example_values(self):
        self.assertTrue(llm.SHARED_PREFIX_BRIDGE.strip())
        self.assertNotIn('"', llm.SHARED_PREFIX_BRIDGE)

    def test_an_unknown_phase_is_refused(self):
        with self.assertRaises(ValueError):
            llm.system_prompt_for_phase(MLE, DSL_DRAFT, "draft", DSL_SYSTEM_PROMPT)


class TestOpenAiKeepsThePerTaskPrompts(unittest.TestCase):
    def test_verify_is_the_small_verify_contract(self):
        out = llm.system_prompt_for_phase(OPENAI, DSL_DRAFT, "verify", VERIFY_PROMPT)
        self.assertEqual(out, VERIFY_PROMPT)
        self.assertFalse(out.startswith(DSL_DRAFT))

    def test_prose_repair_is_the_small_prose_contract(self):
        out = llm.system_prompt_for_phase(OPENAI, DSL_DRAFT, "prose_repair", PROSE_TASK)
        self.assertEqual(out, PROSE_TASK)
        self.assertFalse(out.startswith(DSL_DRAFT))

    def test_json_depth_is_the_json_contract_alone(self):
        out = llm.system_prompt_for_phase(OPENAI, DSL_DRAFT, "json_depth", SYSTEM_PROMPT)
        self.assertEqual(out, SYSTEM_PROMPT)

    def test_api_aliases_are_openai_too(self):
        for provider in ("xai", "grok", "api", "OpenAI"):
            out = llm.system_prompt_for_phase({"provider": provider}, DSL_DRAFT, "verify", VERIFY_PROMPT)
            self.assertEqual(out, VERIFY_PROMPT, provider)


class TestTheDraftPromptIsNeverChanged(unittest.TestCase):
    def test_the_helper_leaves_its_input_and_the_module_contracts_alone(self):
        draft = f"{DSL_SYSTEM_PROMPT.rstrip()}\n\n{THEME_BLOCK}"
        before = str(draft)
        for config in (MLE, LLAMA, OPENAI):
            for phase, task in (("verify", VERIFY_PROMPT), ("prose_repair", PROSE_TASK), ("json_depth", SYSTEM_PROMPT)):
                llm.system_prompt_for_phase(config, draft, phase, task)
        self.assertEqual(draft, before)
        self.assertEqual(DSL_SYSTEM_PROMPT, _DSL_AT_IMPORT)
        self.assertEqual(SYSTEM_PROMPT, _SYSTEM_AT_IMPORT)
        self.assertIs(llm.DSL_SYSTEM_PROMPT, DSL_SYSTEM_PROMPT)
        self.assertIs(llm.SYSTEM_PROMPT, SYSTEM_PROMPT)


# ---------------------------------------------------------------------------
# 2. Through generate_turn: the draft sends its own prompt, everything after shares it
# ---------------------------------------------------------------------------
_CONTEXT = {"player": {"name": "Ash"}, "turn_plan": {"turn_kind": "player_action"}}
_SHORT = "You stand in the yard. Rain falls on the stones."


class _PipelineCase(unittest.TestCase):
    def setUp(self):
        llm.reset_verifier_breaker()
        # Force the model verifier so the turn has a verify call to inspect.
        os.environ["AI_RPG_FAST_VERIFICATION"] = "0"

    def tearDown(self):
        os.environ.pop("AI_RPG_FAST_VERIFICATION", None)
        llm.reset_verifier_breaker()

    def _run(self, config, *, dsl: bool = True):
        """Return [(phase, system_prompt)] for every model call the turn made."""
        calls: list[tuple[str, str]] = []

        def fake_text(system_prompt, *_args, **kwargs):
            calls.append((kwargs.get("phase"), system_prompt))
            if kwargs.get("phase") == "draft_dsl":
                return f"===NAR===\n{_SHORT}\n===OPS===\n"
            return _long_scene()

        def fake_json(system_prompt, *_args, **kwargs):
            phase = kwargs.get("phase")
            calls.append((phase, system_prompt))
            if phase == "verify":
                return {"verdict": "pass", "issues": [], "patch": {}}
            return {
                "scene_plan": {"goal": "look", "focus_points": [{"kind": "scene", "summary": "yard"}]},
                "narration_segments": [{"label": "scene", "text": _SHORT}],
                "player": {},
                "self_check": {"passed": True, "issues_found": [], "corrections_made": []},
                "turn_summary": "looked",
                "scene_focus": "action",
            }

        with mock.patch.object(llm, "get_model_config", side_effect=lambda **_kw: dict(config)), mock.patch.object(
            llm, "_chat_text", side_effect=fake_text
        ), mock.patch.object(llm, "_chat_json", side_effect=fake_json), mock.patch.object(
            llm, "draft_mode_enabled", return_value=dsl
        ), mock.patch.object(llm, "pipeline_enabled", return_value=False):
            llm.generate_turn(dict(_CONTEXT), "I look around")
        return calls


class TestLocalTurnSharesOnePrefix(_PipelineCase):
    def test_the_dsl_draft_sends_the_dsl_contract_unchanged(self):
        calls = self._run(MLE)
        self.assertEqual(calls[0][0], "draft_dsl")
        self.assertEqual(calls[0][1], DSL_SYSTEM_PROMPT)

    def test_every_later_call_starts_with_the_draft_prompt(self):
        calls = self._run(MLE)
        phases = [phase for phase, _ in calls]
        self.assertIn("verify", phases)
        self.assertGreater(len(calls), 2, "the short draft should have triggered a depth repair")
        draft_prompt = calls[0][1]
        for phase, system in calls[1:]:
            self.assertTrue(system.startswith(draft_prompt), f"{phase} does not share the draft prefix")
            self.assertNotEqual(system, draft_prompt, f"{phase} carries no contract of its own")

    def test_the_verify_call_ends_with_the_verify_contract(self):
        calls = self._run(MLE)
        verify = next(system for phase, system in calls if phase == "verify")
        self.assertTrue(verify.endswith(VERIFY_PROMPT))

    def test_the_prose_repair_ends_with_the_prose_contract(self):
        calls = self._run(MLE)
        repairs = [system for phase, system in calls if phase not in {"draft_dsl", "verify"}]
        self.assertTrue(repairs)
        for system in repairs:
            self.assertTrue(system.endswith(PROSE_REPAIR_SYSTEM_PROMPT))

    def test_a_json_draft_turn_shares_the_json_contract_as_its_prefix(self):
        calls = self._run(MLE, dsl=False)
        self.assertEqual(calls[0][0], "draft")
        self.assertEqual(calls[0][1], SYSTEM_PROMPT)
        for phase, system in calls[1:]:
            self.assertTrue(system.startswith(SYSTEM_PROMPT), phase)

    def test_the_trace_records_the_shared_prefix(self):
        with mock.patch.object(llm, "get_model_config", side_effect=lambda **_kw: dict(MLE)):
            self.assertTrue(llm.shares_prompt_prefix(llm.get_model_config()))
        with mock.patch.object(llm, "get_model_config", side_effect=lambda **_kw: dict(OPENAI)):
            self.assertFalse(llm.shares_prompt_prefix(llm.get_model_config()))


class TestOpenAiTurnKeepsSmallPrompts(_PipelineCase):
    def test_the_draft_is_unchanged_and_later_calls_do_not_carry_it(self):
        calls = self._run(OPENAI)
        self.assertEqual(calls[0], ("draft_dsl", DSL_SYSTEM_PROMPT))
        verify = next(system for phase, system in calls if phase == "verify")
        self.assertEqual(verify, VERIFY_PROMPT)
        repairs = [system for phase, system in calls if phase not in {"draft_dsl", "verify"}]
        self.assertTrue(repairs)
        for system in repairs:
            self.assertFalse(system.startswith(DSL_SYSTEM_PROMPT))
            self.assertTrue(system.startswith(PROSE_REPAIR_SYSTEM_PROMPT.split("\n", 1)[0]))


if __name__ == "__main__":
    unittest.main()
