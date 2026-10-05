"""
Playtest #36 (live Qwen3 8B smoke run): auto context overcommitted a 12 GB card.

With llama_cpp_context=auto the server opened Qwen3-8B-Q4_K_M with a 38,912
token window (server.log: "n_ctx_seq (38912) < n_ctx_train (40960)") on an
RTX 4070 Ti (12,282 MiB) that already had 1,100 MiB in use by the desktop. The
plan was 92% of the card (weights + 5.6 GB of cache + a fixed 900 MiB) on top
of what others held, and the first setup call sat in llama_decode for twenty
minutes. 16,384 ran turns in 18-32 s.

The numbers below are the real model's header facts and the card's sizes.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import model_limits as ml  # noqa: E402

MiB = 1024 * 1024
QWEN3_8B_Q4 = {"kind": "gguf", "params_b": 8.0, "n_ctx_train": 40960, "kv_bytes_per_token": 147456, "file_bytes": 5027783488}
RTX_4070_TI_TOTAL = 12282 * MiB


class AutoContextFitsWhatIsFree(unittest.TestCase):
    def ctx(self, free_mib: int, **gpu) -> int:
        return ml.auto_context_tokens(QWEN3_8B_Q4, {"total_bytes": RTX_4070_TI_TOTAL, "free_bytes": free_mib * MiB, **gpu})[0]

    def test_live_card_stays_under_a_safe_window(self):
        ctx = self.ctx(10895)
        self.assertLessEqual(ctx, 24576)
        self.assertGreaterEqual(ctx, ml.PREFERRED_MIN_CONTEXT)

    def test_the_plan_fits_in_what_is_free(self):
        for free in (10895, 8000, 7000):
            ctx = self.ctx(free)
            plan = QWEN3_8B_Q4["file_bytes"] + ctx * QWEN3_8B_Q4["kv_bytes_per_token"]
            self.assertLess(plan, free * MiB, f"free={free} MiB ctx={ctx}")

    def test_less_free_memory_means_a_smaller_window(self):
        roomy, tight, cramped = self.ctx(10895), self.ctx(7000), self.ctx(6000)
        self.assertGreater(roomy, tight)
        self.assertGreater(tight, cramped)
        self.assertEqual(self.ctx(1), ml.MIN_CONTEXT_TOKENS)

    def test_memory_this_process_already_holds_counts_as_free(self):
        # Re-resolving while our own model is loaded must not shrink the window.
        held = QWEN3_8B_Q4["file_bytes"] + 16384 * QWEN3_8B_Q4["kv_bytes_per_token"]
        loaded = self.ctx(10895 - held // MiB, held_bytes=held)
        self.assertEqual(loaded, self.ctx(10895))

    def test_overhead_grows_with_the_window(self):
        self.assertGreater(ml.runtime_overhead_bytes(32768), ml.runtime_overhead_bytes(8192))


if __name__ == "__main__":
    unittest.main()
