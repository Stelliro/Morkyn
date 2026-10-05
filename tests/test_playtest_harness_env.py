"""
Playtest #38: tools/playtest_setup_presets.py tested a game the player does not run.

The harness started its server with path isolation and the model only, so the
narration pipeline, consolidation, fast verification and DSL skip-verify were
all at their shipped defaults (off), while the player's launcher turns them on.
The live smoke run showed the difference: the same model wrote <slot>
placeholders without the launcher env (round 1) and a different draft shape with
it (round 2). It also wrote reports into data/playtest_reports, and left the idea
bank, launcher prefs, skill library and content packs pointing at data/.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import playtest_setup_presets as harness  # noqa: E402

LIVE_DATA = (ROOT / "data").resolve()


def under(path: str, root: Path) -> bool:
    try:
        Path(path).resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


class IsolatedEnvCoversEveryStore(unittest.TestCase):
    def test_every_store_is_inside_the_temp_dir(self):
        tmp = Path(tempfile.mkdtemp(prefix="morkyn-harness-"))
        env = harness.isolated_data_env(str(tmp))
        for key in (
            "AI_RPG_DB",
            "AI_RPG_CAMPAIGN_SLOTS",
            "AI_RPG_IDEA_BANK",
            "AI_RPG_LAUNCHER_PREFS",
            "AI_RPG_SKILL_LIBRARY",
            "AI_RPG_PACK_DIR",
        ):
            self.assertIn(key, env)
            self.assertTrue(under(env[key], tmp), f"{key}={env[key]}")


class LauncherEnv(unittest.TestCase):
    PREFS = {
        "llama_cpp_context": "auto",
        "llama_cpp_flash_attn": True,
        "soft_response_tokens": 1000,
        "hard_response_tokens": 1500,
        "draft_mode": "dsl",
        "narration_pipeline": True,
        "narration_consolidate": True,
        "fast_verification": True,
        "dsl_skip_verify": True,
    }

    def test_maps_like_the_launcher(self):
        env = harness.launcher_env(self.PREFS)
        self.assertEqual(env["AI_RPG_NARRATION_PIPELINE"], "1")
        self.assertEqual(env["AI_RPG_NARRATION_PIPELINE_CONSOLIDATE"], "1")
        self.assertEqual(env["AI_RPG_FAST_VERIFICATION"], "1")
        self.assertEqual(env["AI_RPG_DSL_SKIP_VERIFY"], "1")
        self.assertEqual(env["AI_RPG_DRAFT_MODE"], "dsl")
        self.assertEqual(env["AI_RPG_LLAMA_CPP_FLASH_ATTN"], "True")
        self.assertEqual(env["AI_RPG_MAX_RESPONSE_TOKENS"], "1000")
        self.assertEqual(env["AI_RPG_RESPONSE_HARD_CAP_TOKENS"], "1500")
        self.assertNotIn("AI_RPG_CONTEXT_TOKENS", env)  # auto
        self.assertEqual(harness.launcher_env({**self.PREFS, "llama_cpp_context": 16384})["AI_RPG_CONTEXT_TOKENS"], "16384")

    def test_start_server_passes_the_launcher_env_and_isolated_paths(self):
        captured = {}

        class FakeProc:
            def terminate(self):
                pass

        def fake_popen(cmd, cwd=None, env=None, stdout=None, stderr=None):
            captured["env"] = dict(env)
            return FakeProc()

        prefs_file = Path(tempfile.mkdtemp(prefix="morkyn-harness-prefs-")) / "launcher_prefs.json"
        prefs_file.write_text("﻿" + json.dumps(self.PREFS), encoding="utf-8")
        with mock.patch.object(harness.subprocess, "Popen", side_effect=fake_popen), mock.patch.object(
            harness.urllib.request, "urlopen", return_value=None
        ), mock.patch.object(harness, "LIVE_LAUNCHER_PREFS", prefs_file), mock.patch.dict(
            os.environ, {"AI_RPG_NARRATION_PIPELINE": "0"}
        ):
            proc, base, data_dir = harness.start_server("model.gguf")
        env = captured["env"]
        self.assertEqual(env["AI_RPG_NARRATION_PIPELINE"], "1")
        self.assertEqual(env["AI_RPG_DSL_SKIP_VERIFY"], "1")
        for key in ("AI_RPG_DB", "AI_RPG_IDEA_BANK", "AI_RPG_LAUNCHER_PREFS", "AI_RPG_SKILL_LIBRARY", "AI_RPG_PACK_DIR"):
            self.assertTrue(under(env[key], Path(data_dir)), key)
            self.assertFalse(under(env[key], LIVE_DATA), key)
        # The copy the server reads is the player's prefs, not the live file.
        self.assertTrue(Path(env["AI_RPG_LAUNCHER_PREFS"]).is_file())


class ReportsStayOutOfData(unittest.TestCase):
    def test_default_out_dir_is_not_under_data(self):
        out = harness.default_out_dir("20261006-000000")
        self.assertFalse(under(out, LIVE_DATA), out)


if __name__ == "__main__":
    unittest.main()
