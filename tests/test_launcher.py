"""The launcher moved from the PowerShell Gatehouse into Python and the game's Settings.

Covers app/launcher_prefs.py (the one table of keys and env vars), the server's
/api/launcher/* endpoints, and morkyn_app.parse_args. Every path is pinned to a
temporary directory, so nothing here touches data/launcher_prefs.json or world.db.
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-launcher-test-"))
_ENV = {
    "AI_RPG_DB": str(_TMP / "world.db"),
    "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
    "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
    "AI_RPG_CONSOLIDATED_FACTS": str(_TMP / "facts.jsonl"),
    "AI_RPG_CAMPAIGN_SLOTS": str(_TMP / "slots"),
    "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
    "AI_RPG_PACK_DIR": str(_TMP / "packs"),
    "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
    "AI_RPG_IDEA_BANK": str(_TMP / "idea_bank"),
    "AI_RPG_LAUNCHER_PREFS": str(_TMP / "launcher_prefs.json"),
}
os.environ.update(_ENV)

from app import launcher_prefs as lp  # noqa: E402

PREFS = Path(_ENV["AI_RPG_LAUNCHER_PREFS"])


def setUpModule() -> None:
    os.environ.update(_ENV)
    assert str(lp.prefs_path()).startswith(str(_TMP)), f"test isolation failed: {lp.prefs_path()!r}"


class TestPrefsFile(unittest.TestCase):
    def tearDown(self) -> None:
        PREFS.unlink(missing_ok=True)

    def test_a_gatehouse_file_with_a_bom_and_network_reach_loads(self):
        """PowerShell writes a BOM and says "network"; the old loader showed defaults for both."""
        PREFS.write_bytes("﻿".encode("utf-8") + json.dumps(
            {"launch_mode": "network", "soft_response_tokens": 1000, "dsl_skip_verify": True}).encode("utf-8"))
        prefs = lp.load_prefs()
        self.assertEqual(prefs["launch_mode"], "lan")
        self.assertEqual(prefs["soft_response_tokens"], 1000)
        self.assertTrue(prefs["dsl_skip_verify"])

    def test_save_keeps_keys_this_module_does_not_know(self):
        PREFS.write_text(json.dumps({"some_future_key": 7, "llm_log_mode": "console"}), encoding="utf-8")
        saved = lp.save_prefs({"app_port": "8088"})
        raw = json.loads(PREFS.read_text(encoding="utf-8"))
        self.assertEqual(raw["some_future_key"], 7)
        self.assertEqual(saved["llm_log_mode"], "console", "a Gatehouse-only key must survive a web save")
        self.assertEqual(saved["app_port"], 8088)

    def test_form_strings_are_coerced(self):
        saved = lp.save_prefs({
            "narration_pipeline": "true",
            "fast_verification": "false",
            "llama_cpp_context": "16384",
            "llama_cpp_gpu_layers": "-1",
            "app_port": "99999",
            "window_mode": "nonsense",
        })
        self.assertIs(saved["narration_pipeline"], True)
        self.assertIs(saved["fast_verification"], False)
        self.assertEqual(saved["llama_cpp_context"], 16384)
        self.assertEqual(saved["llama_cpp_gpu_layers"], -1)
        self.assertEqual(saved["app_port"], 65535)
        self.assertEqual(saved["window_mode"], "app")
        self.assertEqual(lp.save_prefs({"llama_cpp_context": "auto"})["llama_cpp_context"], "auto")

    def test_gatehouse_open_browser_off_means_server_only(self):
        PREFS.write_text(json.dumps({"open_browser": False}), encoding="utf-8")
        self.assertEqual(lp.load_prefs()["window_mode"], "none")


class TestRestartKeys(unittest.TestCase):
    def test_live_settings_need_no_restart(self):
        before = lp.default_prefs()
        after = {**before, "narration_pipeline": True, "draft_mode": "json", "mle_model": "other", "model_provider": "openai"}
        self.assertEqual(lp.restart_keys_changed(before, after), [])

    def test_reach_and_port_need_a_restart(self):
        before = lp.default_prefs()
        after = {**before, "launch_mode": "lan", "app_port": 8001}
        self.assertEqual(lp.restart_keys_changed(before, after), ["app_port", "launch_mode"])

    def test_llama_flags_only_count_for_llama(self):
        before = lp.default_prefs()
        self.assertEqual(lp.restart_keys_changed(before, {**before, "llama_cpp_gpu_layers": 10}), [])
        llama = {**before, "model_provider": "llama_cpp"}
        self.assertEqual(lp.restart_keys_changed(llama, {**llama, "llama_cpp_gpu_layers": 10}), ["llama_cpp_gpu_layers"])
        self.assertEqual(lp.restart_keys_changed(before, llama), ["model_provider"])


class TestEnvMapping(unittest.TestCase):
    def test_every_gatehouse_variable_is_mapped(self):
        """The variables Morkyn.ps1 Apply-PrefsToEnvironment set, so the window starts the same server."""
        env = lp.prefs_to_env({**lp.default_prefs(), "soft_response_tokens": 900, "llama_cpp_context": 16384,
                               "dsl_skip_verify": True})
        for key in ("AI_RPG_LAUNCH_MODE", "AI_RPG_APP_PORT", "AI_RPG_MODEL_PROVIDER", "MLE_MODEL",
                    "AI_RPG_LLAMA_CPP_GPU_LAYERS", "AI_RPG_LLAMA_CPP_FLASH_ATTN", "AI_RPG_LLM_LOG_MODE",
                    "AI_RPG_DRAFT_MODE", "AI_RPG_NARRATION_PIPELINE", "AI_RPG_NARRATION_PIPELINE_CONSOLIDATE",
                    "AI_RPG_FAST_VERIFICATION", "AI_RPG_DSL_SKIP_VERIFY", "AI_RPG_LLM_STARTUP_TIMEOUT"):
            self.assertIsNotNone(env.get(key), key)
        self.assertEqual(env["AI_RPG_MAX_RESPONSE_TOKENS"], "900")
        self.assertEqual(env["AI_RPG_CONTEXT_TOKENS"], "16384")
        self.assertEqual(env["AI_RPG_DSL_SKIP_VERIFY"], "1")
        self.assertIsNone(env["AI_RPG_RESPONSE_HARD_CAP_TOKENS"], "0 means auto: the variable must be unset")

    def test_auto_context_unsets_the_override(self):
        target = {"AI_RPG_CONTEXT_TOKENS": "8192"}
        lp.apply_env(lp.prefs_to_env(lp.default_prefs()), target)
        self.assertNotIn("AI_RPG_CONTEXT_TOKENS", target)

    def test_a_running_server_does_not_rewrite_its_own_port(self):
        with mock.patch.dict(os.environ, {"AI_RPG_APP_PORT": "8000"}):
            lp.apply_prefs_to_env({**lp.default_prefs(), "app_port": 9000})
            self.assertEqual(os.environ["AI_RPG_APP_PORT"], "8000")


class TestServerEndpoints(unittest.TestCase):
    """The route functions called directly (the venv has no httpx for TestClient)."""

    @classmethod
    def setUpClass(cls) -> None:
        from app import main

        cls.main = main

    def tearDown(self) -> None:
        PREFS.unlink(missing_ok=True)

    def test_status_reports_pending_restart(self):
        main = self.main
        with mock.patch.object(main, "update_model_config"):
            main.api_launcher_prefs_set(main.LauncherPrefsRequest(prefs={"app_port": 8123}, apply_env=False))
        self.assertIn("app_port", main.api_launcher_status()["restart_pending"])
        prefs = main.api_launcher_prefs_get()
        self.assertIn("defaults", prefs)
        self.assertEqual(prefs["prefs"]["app_port"], 8123)

    def test_restart_refuses_without_the_launcher(self):
        from fastapi import HTTPException

        with mock.patch.dict(os.environ, {"AI_RPG_SUPERVISED": ""}):
            with self.assertRaises(HTTPException) as caught:
                self.main.api_launcher_restart()
        self.assertEqual(caught.exception.status_code, 409)

    def test_restart_under_the_launcher_writes_the_flag(self):
        flag = _TMP / "restart.request"
        with mock.patch.dict(os.environ, {"AI_RPG_SUPERVISED": "1", "AI_RPG_RESTART_FLAG": str(flag)}), \
                mock.patch("threading.Thread.start") as start:
            res = self.main.api_launcher_restart()
        self.assertTrue(res["restarting"])
        self.assertTrue(flag.is_file())
        start.assert_called_once()  # the shutdown thread, which must not run inside a test


class TestArgs(unittest.TestCase):
    def test_gatehouse_words_still_work(self):
        import morkyn_app

        opts = morkyn_app.parse_args(["lan", "8088", "play"])
        self.assertEqual(opts["overrides"], {"launch_mode": "lan", "app_port": 8088})
        self.assertFalse(opts["console"])
        self.assertTrue(morkyn_app.parse_args(["--console"])["console"])
        self.assertEqual(morkyn_app.parse_args(["--browser"])["window"], "browser")


if __name__ == "__main__":
    unittest.main()
