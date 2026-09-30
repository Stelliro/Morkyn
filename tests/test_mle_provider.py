"""MLE is the local provider. A chat call fails in the open until the welding rig is tied in."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_TMP = Path(tempfile.mkdtemp(prefix="morkyn-mle-test-"))
os.environ["AI_RPG_DB"] = str(_TMP / "world.db")

from app.llm import _normalize_provider, apply_theme_model_routing
from app.mle import MleNotReady, chat, status


class TestMleProvider(unittest.TestCase):
    def test_known_providers_stay(self):
        self.assertEqual(_normalize_provider("mle"), "mle")
        self.assertEqual(_normalize_provider("llama_cpp"), "llama_cpp")
        self.assertEqual(_normalize_provider("openai"), "openai")
        self.assertEqual(_normalize_provider("xai"), "openai")

    def test_blank_or_unknown_is_mle(self):
        self.assertEqual(_normalize_provider(""), "mle")
        self.assertEqual(_normalize_provider("local-engine"), "mle")

    def test_theme_routing_sets_mle_model(self):
        out = apply_theme_model_routing(
            {
                "provider": "mle",
                "mle_model": "qwen3:8b",
                "theme_adapter_map": {"isekai_rpg": "morkyn-isekai-dm"},
            },
            {"adapter_hint": "isekai_rpg"},
        )
        self.assertEqual(out["mle_model"], "morkyn-isekai-dm")

    def test_chat_is_not_ready(self):
        with self.assertRaises(MleNotReady):
            chat("system", "user", model="qwen3:8b")

    def test_status_is_not_ok(self):
        report = status("qwen3:8b")
        self.assertFalse(report["ok"])
        self.assertEqual(report["engine"], "MLE")
        self.assertIn("welding rig", str(report["detail"]))


if __name__ == "__main__":
    unittest.main()
