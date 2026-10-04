"""
Failsafes: a model failure becomes a problem the player can act on, and the
MLE loader asks before shrinking the context instead of doing it silently.

The quiet fallback was the complaint: the console said
``n_ctx_seq (8192) < n_ctx_train (32768)`` and the game carried on with a
quarter of the window, while a dead server produced a raw exception string in
the scene box. Now the loader stops at the requested size, the API hands the
browser a problem with tips and a "continue anyway" offer, and the fallback
runs only once the player has accepted it (or AI_RPG_CONTEXT_FALLBACK=auto).
"""

import os
import unittest
from unittest import mock

from app import failsafe, mle


class ClassifyTests(unittest.TestCase):
    def test_memory_errors_get_memory_tips_and_a_turn_fallback(self):
        problem = failsafe.classify_failure("ggml_backend_cuda_buffer_type_alloc_buffer: failed to allocate 9 GiB", stage="turn")
        self.assertEqual(problem["code"], "out_of_memory")
        self.assertTrue(any("RAM" in tip for tip in problem["tips"]))
        self.assertEqual(problem["fallback"]["kind"], "turn_fallback")

    def test_load_stage_has_no_turn_fallback(self):
        problem = failsafe.classify_failure("Connection refused", stage="load")
        self.assertEqual(problem["code"], "server_unreachable")
        self.assertIsNone(problem["fallback"])

    def test_missing_model_message_from_mle(self):
        text = mle.missing_model_detail("qwen3:8b")
        self.assertEqual(failsafe.classify_failure(text, stage="load")["code"], "model_missing")

    def test_unknown_still_has_tips_and_detail(self):
        problem = failsafe.classify_failure("weird failure 0xDEAD")
        self.assertEqual(problem["code"], "unknown")
        self.assertTrue(problem["tips"])
        self.assertEqual(problem["detail"], "weird failure 0xDEAD")

    def test_problem_detail_carries_both_message_and_problem(self):
        detail = failsafe.problem_detail(failsafe.classify_failure("timed out"))
        self.assertIn("message", detail)
        self.assertEqual(detail["problem"]["code"], "timeout")


class _FakeModel:
    def __init__(self, n_ctx):
        self.n_ctx = n_ctx

    def close(self):
        pass


def _fake_open(path, n_ctx):
    if n_ctx > mle._FALLBACK_CONTEXT:
        raise RuntimeError("llama_kv_cache: failed to allocate buffer")
    return _FakeModel(n_ctx)


class ContextGateTests(unittest.TestCase):
    def setUp(self):
        mle._drop_model()
        mle.allow_context_fallback(False)
        mle._LAST_PROBLEM = None
        self.env = mock.patch.dict(os.environ, {"AI_RPG_CONTEXT_TOKENS": "32768", "AI_RPG_CONTEXT_FALLBACK": "ask"})
        self.env.start()
        self.opener = mock.patch.object(mle, "_open_model", side_effect=_fake_open)
        self.opener.start()

    def tearDown(self):
        self.opener.stop()
        self.env.stop()
        mle._drop_model()
        mle.allow_context_fallback(False)
        mle._LAST_PROBLEM = None

    def test_requested_size_fails_and_the_loader_asks_instead_of_shrinking(self):
        with self.assertRaises(mle.MleNotReady) as caught:
            mle._ensure_loaded(mle.Path("model.gguf"))
        problem = caught.exception.problem
        self.assertEqual(problem["code"], "context_too_large")
        self.assertEqual(problem["fallback"]["url"], failsafe.MLE_FALLBACK_ENDPOINT)
        self.assertIn("8,192", problem["fallback"]["label"])
        self.assertIsNone(mle._MODEL)
        self.assertEqual(mle.last_problem()["code"], "context_too_large")

    def test_accepting_the_fallback_loads_the_smaller_context(self):
        mle.allow_context_fallback(True)
        mle._ensure_loaded(mle.Path("model.gguf"))
        self.assertEqual(mle._MODEL_CTX, mle._FALLBACK_CONTEXT)
        self.assertIn("32768 did not load", mle._DETAIL)
        self.assertIsNone(mle.last_problem())

    def test_auto_policy_keeps_the_old_behaviour(self):
        with mock.patch.dict(os.environ, {"AI_RPG_CONTEXT_FALLBACK": "auto"}):
            mle._ensure_loaded(mle.Path("model.gguf"))
        self.assertEqual(mle._MODEL_CTX, mle._FALLBACK_CONTEXT)

    def test_a_requested_size_at_or_below_the_fallback_never_asks(self):
        with mock.patch.dict(os.environ, {"AI_RPG_CONTEXT_TOKENS": "8192"}):
            mle._ensure_loaded(mle.Path("model.gguf"))
        self.assertEqual(mle._MODEL_CTX, 8192)


if __name__ == "__main__":
    unittest.main()
