"""A save in LLM details reaches the launcher prefs the Gatehouse reads.

Stell (2026-10-23): the Gatehouse at the bottom of the main menu "stays as
default" after choosing "Cloud / agent API". /api/launcher-prefs pushed the
engine into the model config, but /api/model-config (LLM details' Save Model)
never wrote back, so the Gatehouse, Settings and the launcher's next start kept
the old engine. app.main._mirror_model_config_to_prefs is the way back.
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
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

os.environ.update(isolated_data_env(tempfile.mkdtemp(prefix="morkyn-model-mirror-")))

from app.launcher_prefs import load_prefs, prefs_path, save_prefs  # noqa: E402
from app.main import _mirror_model_config_to_prefs  # noqa: E402


class ModelConfigMirrorsPrefs(unittest.TestCase):
    def setUp(self):
        # apply_prefs_to_env writes AI_RPG_* into os.environ; other tests must not see it.
        self._env = mock.patch.dict(os.environ, {"AI_RPG_LAUNCHER_PREFS": str(Path(tempfile.mkdtemp(prefix="morkyn-mirror-")) / "prefs.json")})
        self._env.start()
        save_prefs({"model_provider": "mle"})

    def tearDown(self):
        self._env.stop()

    def test_the_cloud_api_chosen_in_llm_details_reaches_the_gatehouse_prefs(self):
        _mirror_model_config_to_prefs({"provider": "openai", "api_model": "grok-4.5", "api_base_url": "https://api.x.ai/v1"})
        prefs = load_prefs()
        self.assertEqual(prefs["model_provider"], "openai")
        self.assertEqual(prefs["api_model"], "grok-4.5")
        self.assertEqual(os.environ.get("AI_RPG_MODEL_PROVIDER"), "openai")

    def test_a_provider_the_launcher_has_no_name_for_is_not_forced_on_it(self):
        _mirror_model_config_to_prefs({"provider": "ollama", "mle_model": "qwen3:8b"})
        self.assertEqual(load_prefs()["model_provider"], "mle")

    def test_a_partial_post_without_engine_fields_leaves_the_prefs_alone(self):
        before = prefs_path().stat().st_mtime_ns
        _mirror_model_config_to_prefs({"lora_path": "", "theme_model_map": {}})
        _mirror_model_config_to_prefs({"provider": "mle"})  # same value: no write
        self.assertEqual(prefs_path().stat().st_mtime_ns, before)


if __name__ == "__main__":
    unittest.main()
