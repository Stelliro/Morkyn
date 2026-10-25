"""The budget's window is the window the in-process model loaded with.

Three runs on an RTX 4070 Ti (12 GB) with Hermes 3 8B Q4_K_M (sonnet100,
stage1, stage2, 2026-10-24/25) opened the model at 14,336 tokens
("n_ctx_seq (14336)"), then printed "context window 10240 / 8192 is too small
for the full system contract" and ran every turn on the compact contract.

Cause: get_model_config() re-resolves the automatic window on every call. After
the load, free VRAM is ~7 GB smaller. resolve_limits adds back an estimate of
what our own model holds (weights + cache + compute per token), but the real use
is larger (CUDA context, scratch), so the re-fit came out one to three steps
smaller, and that number reached fitting_system_prompts. The full contract also
needs 10,272 + 2,048 = 12,320 tokens, one past the old PREFERRED_MIN_CONTEXT of
12,288, so even a one-step drop chose the compact contract.

The facts below are the machine's and the model's; no GPU and no model are used.

Run:  python tools/run_suite.py (or python -m unittest tests.test_context_window_loaded)
"""
from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-ctx-loaded-test-"))
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

from app import db, llm, mle, model_limits as ml  # noqa: E402
from app.prompts import SYSTEM_PROMPT  # noqa: E402

MiB = 2**20
GIB = 2**30
TOTAL = 12282 * MiB  # RTX 4070 Ti as nvidia-smi reports it
FREE_BEFORE = 9 * GIB
WEIGHTS = 4_920_000_000
KV_PER_TOKEN = 2 * 32 * 8 * 128 * 2  # Llama 3.1 8B, f16 cache
PATH = str(_TMP / "Hermes-3-Llama-3.1-8B.Q4_K_M.gguf")
META = {
    "file_bytes": WEIGHTS,
    "general.architecture": "llama",
    "general.name": "Hermes 3 Llama 3.1 8B",
    "general.parameter_count": 8.03e9,
    "llama.context_length": 131072,
    "llama.block_count": 32,
    "llama.embedding_length": 4096,
    "llama.attention.head_count": 32,
    "llama.attention.head_count_kv": 8,
}
CFG = {"provider": "mle", "mle_model": PATH}


def setUpModule():
    os.environ.update(_ENV)
    assert str(db.db_path()).startswith(str(_TMP)), db.db_path()
    db.init_db()


@contextlib.contextmanager
def machine(free_bytes: int, loaded: int = 0, loaded_path: str = PATH):
    gpu = {"total_bytes": TOTAL, "free_bytes": int(free_bytes)}
    patches = [
        mock.patch.dict(os.environ, {"AI_RPG_CONTEXT_TOKENS": ""}),
        mock.patch.object(ml, "gpu_memory", lambda refresh=False: dict(gpu)),
        mock.patch.object(ml, "_gguf_path_for", lambda cfg: Path(PATH)),
        mock.patch.object(ml, "read_gguf_metadata", lambda path: dict(META)),
        mock.patch.object(ml, "_file_size", lambda path: WEIGHTS),
        mock.patch.object(ml, "stored_limits", lambda key: None),
        mock.patch.object(mle, "_MODEL", object() if loaded else None),
        mock.patch.object(mle, "_MODEL_PATH", loaded_path if loaded else ""),
        mock.patch.object(mle, "_MODEL_CTX", int(loaded)),
        mock.patch.object(mle, "_MODEL_CTX_AUTO", bool(loaded)),
        mock.patch.object(llm, "_WARNED_COMPACT_CONTRACT", False),
    ]
    with contextlib.ExitStack() as stack:
        for patch in patches:
            stack.enter_context(patch)
        yield


def free_after_load(n_ctx: int, unseen_mib: int = 900) -> int:
    """Free VRAM once our model is open: its estimated use plus what the estimate misses."""
    estimate = WEIGHTS + n_ctx * KV_PER_TOKEN + n_ctx * ml.COMPUTE_BYTES_PER_TOKEN
    return FREE_BEFORE - estimate - unseen_mib * MiB


def turn_window() -> tuple[int, bool, str]:
    """(window, compact chosen, console) the way a turn reads them."""
    config = llm._overlay_model_limits(dict(CFG))
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        _system, _verify, degraded = llm.fitting_system_prompts(config)
        if degraded:
            llm._warn_compact_contract_once(llm.context_window_tokens(config))
    return llm.context_window_tokens(config), degraded, err.getvalue()


class PreferredMinimumHoldsTheFullContract(unittest.TestCase):
    def test_preferred_minimum_holds_the_contract_and_the_turn(self):
        needed = llm.estimated_tokens(SYSTEM_PROMPT) + llm.MIN_TURN_HEADROOM_TOKENS
        self.assertGreaterEqual(ml.full_contract_context(), needed)
        self.assertGreaterEqual(ml.PREFERRED_MIN_CONTEXT, ml.full_contract_context())


class BeforeTheLoad(unittest.TestCase):
    def test_auto_picks_at_least_the_preferred_minimum(self):
        with machine(FREE_BEFORE):
            limits = ml.resolve_limits(dict(CFG), with_facts=False)
            self.assertEqual(limits["source"]["context_tokens"], "auto")
            self.assertGreaterEqual(limits["context_tokens"], ml.PREFERRED_MIN_CONTEXT)
            window, degraded, console = turn_window()
        self.assertGreaterEqual(window, ml.PREFERRED_MIN_CONTEXT)
        self.assertFalse(degraded)
        self.assertEqual(console, "")

    def test_the_loader_asks_for_the_window_the_budget_uses(self):
        with machine(FREE_BEFORE):
            budget = ml.resolve_limits(dict(CFG), with_facts=False)["context_tokens"]
            with mock.patch("app.llm.get_model_config", lambda **kw: dict(CFG)):
                requested, automatic = mle._context_request()
        self.assertEqual(requested, budget)
        self.assertTrue(automatic)


class AfterTheLoad(unittest.TestCase):
    def setUp(self):
        with machine(FREE_BEFORE):
            self.opened = ml.resolve_limits(dict(CFG), with_facts=False)["context_tokens"]

    def test_window_is_the_loaded_context_and_the_full_contract_runs(self):
        for unseen in (0, 300, 700, 900, 1300):
            with self.subTest(unseen_mib=unseen), machine(free_after_load(self.opened, unseen), loaded=self.opened):
                self.assertEqual(ml.resolve_limits(dict(CFG), with_facts=False)["context_tokens"], self.opened)
                window, degraded, console = turn_window()
                self.assertEqual(window, self.opened)
                self.assertFalse(degraded)
                self.assertNotIn("compact contract", console)

    def test_the_loader_keeps_the_open_model(self):
        with machine(free_after_load(self.opened), loaded=self.opened):
            with mock.patch("app.llm.get_model_config", lambda **kw: dict(CFG)):
                requested, automatic = mle._context_request()
        self.assertEqual(requested, self.opened)
        self.assertTrue(automatic)

    def test_a_stale_automatic_number_does_not_shrink_the_loaded_window(self):
        stale = {**CFG, "context_window": 8192, "model_limits": {"source": {"context_tokens": "auto"}}}
        with machine(free_after_load(self.opened), loaded=self.opened):
            self.assertEqual(llm.context_window_tokens(stale), self.opened)
            _s, _v, degraded = llm.fitting_system_prompts(stale)
        self.assertFalse(degraded)

    def test_a_number_someone_set_still_caps_the_window(self):
        chosen = {**CFG, "context_window": 8192, "model_limits": {"source": {"context_tokens": "custom"}}}
        with machine(free_after_load(self.opened), loaded=self.opened):
            self.assertEqual(llm.context_window_tokens(chosen), 8192)

    def test_another_file_loaded_is_not_pinned(self):
        with machine(free_after_load(self.opened, 0), loaded=self.opened, loaded_path=str(_TMP / "other.gguf")):
            self.assertEqual(ml._loaded_auto_context(ml.model_facts(dict(CFG))), 0)


class SmallMachineStaysCompact(unittest.TestCase):
    def test_a_fit_of_6144_chooses_the_compact_contract_and_says_so(self):
        tokens = 6144 * (KV_PER_TOKEN + ml.COMPUTE_BYTES_PER_TOKEN) + 100 * MiB
        free = WEIGHTS + ml.RUNTIME_OVERHEAD_BYTES + tokens + ml.GPU_HEADROOM_BYTES
        with machine(free):
            self.assertEqual(ml.resolve_limits(dict(CFG), with_facts=False)["context_tokens"], 6144)
            window, degraded, console = turn_window()
        self.assertEqual(window, 6144)
        self.assertTrue(degraded)
        self.assertIn("context window 6144", console)
        self.assertIn(str(llm.estimated_tokens(SYSTEM_PROMPT)), console)
        with machine(max(0, free - WEIGHTS - 6144 * KV_PER_TOKEN), loaded=6144):
            window_after, degraded_after, _console = turn_window()
        self.assertEqual(window_after, 6144)
        self.assertTrue(degraded_after)


if __name__ == "__main__":
    unittest.main()
