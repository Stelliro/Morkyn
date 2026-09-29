"""API bodies the setup/model UI actually posts must survive the route models.

Run: python -m unittest tests.test_api_ui_contracts
"""
from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pydantic import ValidationError  # noqa: E402

from app.image_backends import (  # noqa: E402
    clamp_slider_lora_weight,
    format_lora_tags,
    resolve_active_loras,
)
from app.main import (  # noqa: E402
    CharacterPromptPreviewRequest,
    CharacterSetRequest,
    LoraWeight,
    ModelConfigRequest,
    api_update_model_config,
)


class TestModelConfigKeepsLlmLoras(unittest.TestCase):
    def test_posted_lora_fields_reach_update_model_config(self):
        raw = {
            "provider": "llama_cpp",
            "lora_path": "D:/loras/always.gguf",
            "theme_llm_lora_map": {
                "isekai_rpg": {"path": "D:/loras/isekai.gguf", "scale": 0.8},
            },
            "theme_adapter_map": {"default": "grok-4.5"},
        }
        dumped = ModelConfigRequest.model_validate(raw).model_dump(exclude_unset=True)
        self.assertEqual(dumped["lora_path"], "D:/loras/always.gguf")
        self.assertEqual(
            dumped["theme_llm_lora_map"]["isekai_rpg"]["path"],
            "D:/loras/isekai.gguf",
        )
        self.assertEqual(dumped["theme_llm_lora_map"]["isekai_rpg"]["scale"], 0.8)
        src = inspect.getsource(api_update_model_config)
        self.assertIn("exclude_unset=True", src)

    def test_partial_post_does_not_invent_empty_lora_path(self):
        dumped = ModelConfigRequest.model_validate({"provider": "openai"}).model_dump(
            exclude_unset=True
        )
        self.assertEqual(dumped.get("provider"), "openai")
        self.assertNotIn("lora_path", dumped)
        self.assertNotIn("theme_llm_lora_map", dumped)


class TestSliderLoraWeightRange(unittest.TestCase):
    def test_age_slider_weight_is_not_rejected_or_squashed(self):
        row = LoraWeight(name="age_slider", weight=3.5)
        self.assertEqual(row.weight, 3.5)
        neg = LoraWeight(name="age_slider", weight=-1.25)
        self.assertEqual(neg.weight, -1.25)
        body = CharacterSetRequest(
            loras=[{"name": "age_slider", "weight": 3.5, "activation_text": "old"}]
        )
        self.assertEqual(body.loras[0].weight, 3.5)
        preview = CharacterPromptPreviewRequest(
            loras=[{"name": "age_slider", "weight": -1.25}]
        )
        self.assertEqual(preview.loras[0].weight, -1.25)
        resolved = resolve_active_loras([{"name": "age_slider", "weight": 3.5}])
        self.assertEqual(resolved[0]["weight"], 3.5)
        self.assertIn("<lora:age_slider:3.5>", format_lora_tags(resolved))
        self.assertEqual(clamp_slider_lora_weight(-1.25), -1.25)
        self.assertEqual(clamp_slider_lora_weight(0), 0.01)
        self.assertEqual(clamp_slider_lora_weight(9), 5.0)
        with self.assertRaises(ValidationError):
            LoraWeight(name="age_slider", weight=9)
        src = (ROOT / "app" / "image_backends.py").read_text(encoding="utf-8")
        self.assertNotIn("max(0.05, min(2.0, wt))", src)
        self.assertNotIn("max(0.05, min(2.0, weight))", src)


if __name__ == "__main__":
    unittest.main()
