"""The model verifier returns a verdict, not a whole turn.

Measured on the 2026-09-23 trace (grok-4.7): the verify pass asked for "a
corrected full turn JSON", overran its token cap at 5,224 characters, and cost
71% of a 107 s turn, nearly all of it narration the draft already had. On a 7B
the same pass echoed the input world_state on 42/42 turns.

The verifier now answers with `verdict` (pass or revise), `issues`, and a
`patch` holding only the turn keys it replaces, with a replacement narration
only when the prose itself is wrong. `_resolve_verified_turn` merges the patch
over the draft and writes `self_check` from the verdict. The legacy full-turn
reply still works, an echo still trips the breaker, and the verify token caps
are well below what a whole turn needed.

Run:  python -m unittest tests.test_verifier_verdict
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-verdict-test-"))
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
from app.prompts import COMPACT_VERIFY_PROMPT, VERIFY_PROMPT, _scene_instruction, build_verify_prompt  # noqa: E402

_BUDGET_ENV = (
    "AI_RPG_TURN_VERIFY_TOKENS",
    "AI_RPG_TURN_DRAFT_TOKENS",
    "AI_RPG_TURN_COMPACT_VERIFY_TOKENS",
    "AI_RPG_VERIFY_FAILURE_LIMIT",
)

# The caps the full-turn verifier needed. The verdict must stay under them.
_OLD_LOCAL_VERIFY_TOKENS = {"concise": 700, "balanced": 950, "rich": 1300, "expansive": 1800}
_OLD_API_VERIFY_TOKENS = {"concise": 1800, "balanced": 2800, "rich": 3600, "expansive": 4800}
_OLD_COMPACT_VERIFY_TOKENS = 700


def setUpModule():
    os.environ.update(_ENV)
    assert str(db.db_path()).startswith(str(_TMP)), db.db_path()
    db.init_db()


def _long_scene(words: int = 260) -> str:
    return " ".join(["You watch the rain cross the yard and wait."] * (words // 9))


def _draft() -> dict:
    scene = _long_scene()
    return {
        "scene_plan": {"goal": "look", "focus_points": [{"kind": "scene", "summary": "yard"}]},
        "narration_segments": [{"label": "scene", "text": scene}],
        "narration": scene,
        "player": {"gold_band": "small"},
        "self_check": {"passed": True, "issues_found": [], "corrections_made": []},
        "turn_summary": "looked at the yard",
        "scene_focus": "action",
        "inventory_changes": [{"name": "Rope", "quantity_band": "small"}],
    }


def _clear_env():
    for key in _BUDGET_ENV:
        os.environ.pop(key, None)


# ---------------------------------------------------------------------------
# 1. A verdict is merged over the draft
# ---------------------------------------------------------------------------
class TestVerdictMerge(unittest.TestCase):
    def setUp(self):
        llm.reset_verifier_breaker()

    tearDown = setUp

    def test_pass_keeps_the_draft(self):
        draft = _draft()
        trace = []
        result = llm._resolve_verified_turn({"verdict": "pass", "issues": [], "patch": {}}, draft, {}, trace)
        self.assertEqual(result["narration"], draft["narration"])
        self.assertEqual(result["inventory_changes"], draft["inventory_changes"])
        self.assertEqual(result["player"], draft["player"])
        self.assertEqual(result["scene_plan"], draft["scene_plan"])
        self.assertEqual(result["turn_summary"], draft["turn_summary"])
        self.assertTrue(result["self_check"]["passed"])
        self.assertEqual(result["self_check"]["issues_found"], [])
        events = {(step.get("phase"), step.get("event")): step for step in trace}
        self.assertEqual(events[("verify", "verifier_reply")]["kind"], "verdict")
        verdict = events[("verify", "verifier_verdict")]
        self.assertTrue(verdict["passed"])
        self.assertEqual(verdict["patched_keys"], [])

    def test_revise_replaces_only_the_patched_keys(self):
        draft = _draft()
        trace = []
        reply = {
            "verdict": "revise",
            "issues": ["The rope was never picked up."],
            "patch": {"inventory_changes": [], "player": {"gold_band": "none"}},
        }
        result = llm._resolve_verified_turn(reply, draft, {}, trace)
        self.assertEqual(result["inventory_changes"], [])
        self.assertEqual(result["player"], {"gold_band": "none"})
        # Everything the patch did not name is the draft's.
        self.assertEqual(result["narration"], draft["narration"])
        self.assertEqual(result["narration_segments"], draft["narration_segments"])
        self.assertEqual(result["scene_plan"], draft["scene_plan"])
        self.assertEqual(result["turn_summary"], draft["turn_summary"])
        self.assertEqual(result["scene_focus"], draft["scene_focus"])
        check = result["self_check"]
        self.assertTrue(check["passed"], "a revise verdict with its patch applied is a consistent turn")
        self.assertEqual(check["issues_found"], ["The rope was never picked up."])
        self.assertTrue(any("inventory_changes" in note for note in check["corrections_made"]))
        self.assertTrue(any("player" in note for note in check["corrections_made"]))
        verdict = next(step for step in trace if step.get("event") == "verifier_verdict")
        self.assertEqual(sorted(verdict["patched_keys"]), ["inventory_changes", "player"])
        self.assertFalse(verdict["narration_replaced"])

    def test_a_replacement_narration_is_used_only_when_sent(self):
        draft = _draft()
        new_prose = " ".join(["You step back from the yard and watch the gate."] * 30)
        trace = []
        result = llm._resolve_verified_turn(
            {"verdict": "revise", "issues": ["prose named the wrong gate"], "patch": {"narration": new_prose}},
            draft,
            {},
            trace,
        )
        self.assertTrue(result["narration"].startswith("You step back"))
        self.assertEqual(len(result["narration_segments"]), 1)
        self.assertEqual(result["inventory_changes"], draft["inventory_changes"])
        self.assertTrue(result["self_check"]["passed"])
        verdict = next(step for step in trace if step.get("event") == "verifier_verdict")
        self.assertTrue(verdict["narration_replaced"])
        self.assertEqual(verdict["patched_keys"], ["narration"])

    def test_an_empty_replacement_narration_keeps_the_draft_prose(self):
        draft = _draft()
        result = llm._resolve_verified_turn(
            {"verdict": "revise", "issues": [], "patch": {"narration": "", "narration_segments": []}}, draft, {}
        )
        self.assertEqual(result["narration"], draft["narration"])
        # Nothing was actually replaced, so a revise verdict is not a pass.
        self.assertFalse(result["self_check"]["passed"])

    def test_revise_without_a_patch_is_not_a_pass(self):
        result = llm._resolve_verified_turn({"verdict": "revise", "issues": ["gold is unjustified"], "patch": {}}, _draft(), {})
        self.assertFalse(result["self_check"]["passed"])
        self.assertIn("gold is unjustified", result["self_check"]["issues_found"])

    def test_unknown_patch_keys_and_self_check_are_ignored(self):
        draft = _draft()
        trace = []
        result = llm._resolve_verified_turn(
            {
                "verdict": "pass",
                "patch": {"self_check": {"passed": False}, "world_state": {"x": 1}, "notes": "ignore me"},
            },
            draft,
            {},
            trace,
        )
        self.assertTrue(result["self_check"]["passed"], "the engine writes self_check from the verdict")
        self.assertNotIn("notes", result)
        verdict = next(step for step in trace if step.get("event") == "verifier_verdict")
        self.assertEqual(sorted(verdict["ignored_keys"]), ["notes", "self_check", "world_state"])

    def test_turn_keys_beside_the_verdict_count_as_the_patch(self):
        result = llm._resolve_verified_turn({"verdict": "revise", "inventory_changes": []}, _draft(), {})
        self.assertEqual(result["inventory_changes"], [])
        self.assertTrue(result["self_check"]["passed"])

    def test_a_wrapped_verdict_is_unwrapped(self):
        result = llm._resolve_verified_turn({"result": {"verdict": "pass", "issues": []}}, _draft(), {})
        self.assertTrue(result["self_check"]["passed"])
        self.assertEqual(llm._verify_reply_kind({"result": {"verdict": "pass"}}), "verdict")

    def test_an_unrecognized_verdict_fails_the_self_check(self):
        result = llm._resolve_verified_turn({"verdict": "maybe", "patch": {}}, _draft(), {})
        self.assertFalse(result["self_check"]["passed"])
        self.assertTrue(any("not pass or revise" in note for note in result["self_check"]["issues_found"]))

    def test_the_self_check_shape_survives_handoff_cleanup(self):
        result = llm._resolve_verified_turn({"verdict": "pass"}, _draft(), {})
        cleaned = llm._clean_turn_for_handoff(result, "verifier_to_world", [])
        self.assertEqual(
            set(cleaned["self_check"]),
            {"passed", "issues_found", "corrections_made", "reference_check", "consistency_check"},
        )
        self.assertTrue(cleaned["self_check"]["passed"])


# ---------------------------------------------------------------------------
# 2. The legacy full-turn reply still works
# ---------------------------------------------------------------------------
class TestLegacyFullTurnReply(unittest.TestCase):
    def setUp(self):
        llm.reset_verifier_breaker()

    tearDown = setUp

    def test_a_full_turn_reply_is_normalized_as_before(self):
        draft = _draft()
        corrected = dict(draft)
        corrected["narration"] = " ".join(["You wait by the yard gate as the rain thins."] * 30)
        corrected["narration_segments"] = [{"label": "scene", "text": corrected["narration"]}]
        corrected["inventory_changes"] = []
        corrected["self_check"] = {"passed": True, "issues_found": [], "corrections_made": ["dropped the rope"]}
        trace = []
        result = llm._resolve_verified_turn(corrected, draft, {}, trace)
        self.assertTrue(result["narration"].startswith("You wait by the yard gate"))
        self.assertEqual(result["inventory_changes"], [])
        # _normalize_turn adds its own deterministic name-repair note after the model's.
        self.assertIn("dropped the rope", result["self_check"]["corrections_made"])
        self.assertEqual(llm._verify_reply_kind(corrected), "legacy")
        self.assertEqual(next(step for step in trace if step.get("event") == "verifier_reply")["kind"], "legacy")

    def test_a_full_turn_reply_without_prose_keeps_the_draft_narration(self):
        draft = _draft()
        result = llm._resolve_verified_turn(
            {"player": {"gold_band": "none"}, "self_check": {"passed": True}, "turn_summary": "fixed"}, draft, {}
        )
        self.assertEqual(result["narration"], draft["narration"])
        self.assertEqual(result["player"], {"gold_band": "none"})
        self.assertEqual(result["turn_summary"], "fixed")

    def test_a_legacy_reply_is_still_useful_output(self):
        self.assertTrue(llm._verified_output_is_useful({"narration": "y" * 1100, "turn_summary": "s"}, _draft()))


# ---------------------------------------------------------------------------
# 3. An echo still trips the breaker; a verdict resets it
# ---------------------------------------------------------------------------
class TestBreakerWithVerdicts(unittest.TestCase):
    def setUp(self):
        llm.reset_verifier_breaker()
        _clear_env()

    tearDown = setUp

    def test_a_verdict_object_is_useful(self):
        draft = _draft()
        self.assertTrue(llm._verified_output_is_useful({"verdict": "pass", "issues": [], "patch": {}}, draft))
        self.assertTrue(llm._verified_output_is_useful({"verdict": "revise", "patch": {"player": {}}}, draft))
        self.assertEqual(llm._verify_reply_kind({"verdict": "pass"}), "verdict")

    def test_an_echo_is_not_useful_even_with_a_verdict_key(self):
        draft = _draft()
        self.assertFalse(llm._verified_output_is_useful({"world_state": {}}, draft))
        self.assertFalse(llm._verified_output_is_useful({"draft_turn": draft}, draft))
        self.assertFalse(llm._verified_output_is_useful({"verdict": "pass", "world_state": {}}, draft))
        self.assertFalse(llm._verified_output_is_useful({"unrelated": 1}, draft))
        self.assertFalse(llm._verified_output_is_useful("not a dict", draft))
        self.assertEqual(llm._verify_reply_kind({"world_state": {}}), "echo")
        self.assertEqual(llm._verify_reply_kind({"unrelated": 1}), "invalid")

    def test_three_echoes_trip_the_breaker_and_one_verdict_resets_it(self):
        draft = _draft()
        for _ in range(3):
            echo = {"world_state": {"player": {}}}
            llm._note_verify_outcome(llm._verified_output_is_useful(echo, draft), "echoed input")
        self.assertTrue(llm.verifier_is_disabled())
        llm._note_verify_outcome(llm._verified_output_is_useful({"verdict": "pass"}, draft))
        self.assertFalse(llm.verifier_is_disabled())

    def test_an_echo_keeps_the_draft(self):
        draft = _draft()
        result = llm._resolve_verified_turn({"world_state": {"player": {}}}, draft, {})
        self.assertEqual(result["narration"], draft["narration"])
        self.assertEqual(result["inventory_changes"], draft["inventory_changes"])


# ---------------------------------------------------------------------------
# 4. The verify cap is lower than a whole turn needed
# ---------------------------------------------------------------------------
class TestVerifyTokenCaps(unittest.TestCase):
    def setUp(self):
        _clear_env()

    tearDown = setUp

    def test_every_verify_cap_is_below_the_full_turn_cap(self):
        for detail, old in _OLD_LOCAL_VERIFY_TOKENS.items():
            self.assertLess(llm.LOCAL_VERIFY_TOKENS[detail], old, detail)
        for detail, old in _OLD_API_VERIFY_TOKENS.items():
            self.assertLess(llm.API_VERIFY_TOKENS[detail], old, detail)

    def test_a_verify_cap_never_exceeds_the_draft_cap(self):
        api = {"provider": "openai", "api_model": "grok-4.7", "response_token_cap": 1500, "response_token_hard_cap": 2000}
        small = {"provider": "mle", "mle_model": "qwen2.5:7b-instruct", "response_token_cap": 1500, "response_token_hard_cap": 2000}
        for detail in ("concise", "balanced", "rich", "expansive"):
            context = {"settings": {"playthrough_options": {"narration_detail": detail}}}
            for config in (api, small):
                self.assertLessEqual(
                    llm._turn_token_default(context, "verify", config),
                    llm._turn_token_default(context, "draft", config),
                    (detail, config["provider"]),
                )

    def test_a_verdict_still_has_room_for_one_replacement_narration(self):
        # MAX_TURN_NARRATION_CHARS at ~4 chars per token, plus the verdict itself.
        self.assertGreaterEqual(llm.LOCAL_VERIFY_TOKENS["rich"], llm.MAX_TURN_NARRATION_CHARS // 4 + 100)

    def test_the_compact_verify_cap_is_lower_too(self):
        self.assertLess(llm._turn_max_tokens({}, "verify", compact=True), _OLD_COMPACT_VERIFY_TOKENS)


# ---------------------------------------------------------------------------
# 5. The prompts ask for a verdict
# ---------------------------------------------------------------------------
class TestVerifyPromptContract(unittest.TestCase):
    def test_both_verify_prompts_ask_for_a_verdict_not_a_turn(self):
        for label, text in (("VERIFY_PROMPT", VERIFY_PROMPT), ("COMPACT_VERIFY_PROMPT", COMPACT_VERIFY_PROMPT)):
            low = text.lower()
            with self.subTest(prompt=label):
                self.assertIn("verdict", low)
                self.assertIn("patch", low)
                self.assertIn("issues", low)
                self.assertNotIn("corrected full turn", low)
                self.assertNotIn("full corrected turn", low)
                self.assertIn("do not return the full turn", low)

    def test_the_checking_instruction_asks_for_a_verdict(self):
        text = _scene_instruction("player_action", {}, checking=True).lower()
        self.assertIn("verdict", text)
        self.assertIn("patch", text)
        self.assertNotIn("full turn json", text)
        self.assertIn("stays out of the patch", text)

    def test_the_verify_prompt_still_carries_the_draft(self):
        draft = _draft()
        prompt = build_verify_prompt({"player": {"name": "Ash"}}, "I look around", draft)
        self.assertIn('"draft_turn"', prompt)
        self.assertIn("Return a verdict object", prompt)


# ---------------------------------------------------------------------------
# 6. Through the turn pipeline, on both draft paths
# ---------------------------------------------------------------------------
class TestVerdictThroughThePipeline(unittest.TestCase):
    def setUp(self):
        llm.reset_verifier_breaker()
        _clear_env()

    tearDown = setUp

    _CONTEXT = {"player": {"name": "Ash"}, "turn_plan": {"turn_kind": "player_action"}}

    def _run_json_path(self, verify_reply):
        calls = []
        draft = _draft()

        def fake_json(*_args, **kwargs):
            calls.append(dict(kwargs))
            phase = kwargs.get("phase")
            if phase == "verify":
                return verify_reply
            return dict(draft)

        with mock.patch.object(llm, "_chat_json", side_effect=fake_json), mock.patch.object(
            llm, "_chat_text", side_effect=llm.LlmError("prose retry should not run")
        ), mock.patch.object(llm, "draft_mode_enabled", return_value=False), mock.patch.object(
            llm, "pipeline_enabled", return_value=False
        ):
            result = llm.generate_turn(dict(self._CONTEXT), "I look around")
        return result, calls, draft

    def test_json_draft_path_applies_a_revise_verdict(self):
        reply = {"verdict": "revise", "issues": ["no rope was gained"], "patch": {"inventory_changes": []}}
        result, calls, draft = self._run_json_path(reply)
        phases = [call.get("phase") for call in calls]
        self.assertIn("verify", phases, "the draft's inventory change must send it to the verifier")
        self.assertFalse(result.get("inventory_changes"))
        self.assertEqual(result["narration"], draft["narration"])
        self.assertTrue(result["self_check"]["passed"])
        self.assertEqual(result["self_check"]["issues_found"], ["no rope was gained"])
        verify_call = next(call for call in calls if call.get("phase") == "verify")
        self.assertLessEqual(verify_call["max_tokens"], max(llm.API_VERIFY_TOKENS.values()))
        events = [(step.get("phase"), step.get("event")) for step in result["_model_trace"]]
        self.assertIn(("verify", "verifier_reply"), events)
        self.assertIn(("verify", "verifier_verdict"), events)
        self.assertFalse(llm.verifier_is_disabled())

    def test_json_draft_path_keeps_the_draft_on_pass(self):
        result, _calls, draft = self._run_json_path({"verdict": "pass", "issues": [], "patch": {}})
        self.assertEqual(result["inventory_changes"], draft["inventory_changes"])
        self.assertEqual(result["narration"], draft["narration"])
        self.assertTrue(result["self_check"]["passed"])

    def test_dsl_draft_path_applies_the_verdict_too(self):
        draft = _draft()
        calls = []

        def fake_json(*_args, **kwargs):
            calls.append(kwargs.get("phase"))
            return {"verdict": "revise", "issues": ["gold unjustified"], "patch": {"player": {"gold_band": "none"}}}

        with mock.patch.object(llm, "_try_dsl_draft", return_value=dict(draft)), mock.patch.object(
            llm, "_chat_json", side_effect=fake_json
        ), mock.patch.object(llm, "_chat_text", side_effect=llm.LlmError("prose retry should not run")), mock.patch.object(
            llm, "pipeline_enabled", return_value=False
        ):
            result = llm.generate_turn(dict(self._CONTEXT), "I look around")
        self.assertEqual(calls, ["verify"])
        self.assertEqual(result["player"].get("gold_band"), "none")
        self.assertEqual(result["narration"], draft["narration"])
        self.assertEqual(result.get("_draft_mode"), "dsl")
        self.assertTrue(result["self_check"]["passed"])

    def test_echo_replies_through_the_pipeline_trip_the_breaker(self):
        for _ in range(3):
            result, calls, draft = self._run_json_path({"world_state": {"player": {}}})
            self.assertEqual(result["narration"], draft["narration"])
        self.assertTrue(llm.verifier_is_disabled())
        _result, calls, _draft = self._run_json_path({"verdict": "pass"})
        self.assertNotIn("verify", [call.get("phase") for call in calls], "the breaker skips the verifier")


class TestCompactVerifyRetryAndTheBreaker(unittest.TestCase):
    """A context overflow the compact retry recovers is a verified turn.

    The breaker used to be charged before the compact retry ran and never
    reset when it succeeded, so three overflow-then-recover turns disabled
    the verifier for the session under a reason blaming unusable output.
    """

    _CONTEXT = {"player": {"name": "Ash"}, "turn_plan": {"turn_kind": "player_action"}}

    def setUp(self):
        llm.reset_verifier_breaker()
        _clear_env()

    tearDown = setUp

    def _run_overflow_turn(self, compact_reply):
        calls = []
        draft = _draft()

        def fake_json(*_args, **kwargs):
            calls.append(kwargs.get("phase"))
            phase = kwargs.get("phase")
            if phase == "verify":
                raise llm.LlmError("This model's maximum context length is 8192 tokens (context_length_exceeded)")
            if phase == "verify_compact_retry":
                if isinstance(compact_reply, Exception):
                    raise compact_reply
                return compact_reply
            return dict(draft)

        with mock.patch.object(llm, "_chat_json", side_effect=fake_json), mock.patch.object(
            llm, "_chat_text", side_effect=llm.LlmError("prose retry should not run")
        ), mock.patch.object(llm, "draft_mode_enabled", return_value=False), mock.patch.object(
            llm, "pipeline_enabled", return_value=False
        ):
            result = llm.generate_turn(dict(self._CONTEXT), "I look around")
        return result, calls, draft

    def test_three_recovered_overflows_leave_the_breaker_untouched(self):
        for _ in range(3):
            result, calls, _draft = self._run_overflow_turn({"verdict": "pass", "issues": [], "patch": {}})
            self.assertIn("verify_compact_retry", calls)
            self.assertTrue(result["self_check"]["passed"], "the compact retry verified the turn")
        self.assertEqual(llm.verifier_breaker_status()["failure_streak"], 0)
        self.assertFalse(llm.verifier_is_disabled())
        _result, calls, _draft = self._run_overflow_turn({"verdict": "pass", "issues": [], "patch": {}})
        self.assertIn("verify", calls, "the fourth turn still reaches the verifier")

    def test_a_recovered_overflow_resets_an_earlier_streak(self):
        llm._note_verify_outcome(False, "echo")
        llm._note_verify_outcome(False, "echo")
        self.assertEqual(llm.verifier_breaker_status()["failure_streak"], 2)
        self._run_overflow_turn({"verdict": "pass", "issues": [], "patch": {}})
        self.assertEqual(llm.verifier_breaker_status()["failure_streak"], 0)

    def test_an_echo_from_the_compact_retry_still_counts_as_a_failure(self):
        self._run_overflow_turn({"world_state": {"player": {}}})
        self.assertEqual(llm.verifier_breaker_status()["failure_streak"], 1)

    def test_an_overflow_the_compact_retry_cannot_recover_counts_once(self):
        result, calls, draft = self._run_overflow_turn(llm.LlmError("still exceeds the available context"))
        self.assertIn("verify_compact_retry", calls)
        self.assertEqual(result["narration"], draft["narration"])
        self.assertFalse(result["self_check"]["passed"])
        self.assertEqual(llm.verifier_breaker_status()["failure_streak"], 1)


if __name__ == "__main__":
    unittest.main()
