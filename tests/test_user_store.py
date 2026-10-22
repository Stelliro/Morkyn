"""The API key and model settings live per user, encrypted where the OS can (Stell, 2026-10-22).

"the api key and settings dont save, we should be saving it in a local encrypted
file that only morkyn can read that we save in appdata or somewhere else secure"

Run:  .venv\\Scripts\\python -m unittest tests.test_user_store
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-user-store-"))
_ENV = isolated_data_env(str(_TMP))
_SAVED_ENV: dict[str, str | None] = {}


def setUpModule():
    _SAVED_ENV.update({key: os.environ.get(key) for key in _ENV})
    os.environ.update(_ENV)


def tearDownModule():
    for key, value in _SAVED_ENV.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


class TheKeyIsKeptPerUserAndNotInPlainText(unittest.TestCase):
    def test_the_store_is_the_isolated_folder_in_tests(self):
        from app import user_store

        self.assertEqual(user_store.user_dir(), _TMP / "user")

    def test_a_secret_round_trips_and_the_file_does_not_hold_it_in_plain_text(self):
        from app import user_store

        user_store.set_secret("api_key", "xai-secret-1234567890")
        self.assertEqual(user_store.get_secret("api_key"), "xai-secret-1234567890")
        raw = (_TMP / "user" / "secrets.bin").read_bytes()
        if user_store.protection() == "dpapi":
            self.assertNotIn(b"xai-secret", raw)
        user_store.set_secret("api_key", "")
        self.assertEqual(user_store.get_secret("api_key"), "")

    def test_saved_settings_survive_another_save_and_hold_no_key(self):
        from app import llm, user_store
        from app.db import connect, init_db

        init_db()
        llm.update_model_config({"provider": "openai", "api_key": "xai-kept-across-saves", "api_model": "grok-4.5"})
        self.assertNotIn("xai-kept", user_store.settings_path().read_text(encoding="utf-8"))
        with connect().closing() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = 'model_config'").fetchone()
        self.assertNotIn("api_key", json.loads(row[0]))
        # A new game's database knows nothing; the per-user settings and key still apply.
        with connect().closing() as conn:
            conn.execute("DELETE FROM settings WHERE key = 'model_config'")
        cfg = llm.get_model_config(ignore_override=True, resolve_limits=False)
        self.assertEqual((cfg["provider"], cfg["api_key"]), ("openai", "xai-kept-across-saves"))

    def test_a_plain_key_an_older_save_held_moves_to_the_store(self):
        from app import llm, user_store
        from app.db import connect, init_db

        init_db()
        user_store.set_secret("api_key", "")
        with connect().closing() as conn:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES ('model_config', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (json.dumps({"provider": "openai", "api_key": "xai-from-an-old-save"}),),
            )
        cfg = llm.get_model_config(ignore_override=True, resolve_limits=False)
        self.assertEqual(cfg["api_key"], "xai-from-an-old-save")
        self.assertEqual(user_store.get_secret("api_key"), "xai-from-an-old-save")


class TheSpeechKeyToo(unittest.TestCase):
    def test_the_speech_key_and_settings_live_per_user(self):
        from app import tts, user_store
        from app.db import connect, init_db

        init_db()
        tts.update_tts_config({"provider": "openai", "enabled": True, "api_key": "sk-proj-speech-key"})
        self.assertEqual(user_store.get_secret("tts_api_key"), "sk-proj-speech-key")
        self.assertNotIn("speech-key", user_store.settings_path("speech").read_text(encoding="utf-8"))
        with connect().closing() as conn:
            conn.execute("DELETE FROM settings WHERE key = ?", (tts.TTS_CONFIG_KEY,))
        cfg = tts.get_tts_config()
        self.assertEqual((cfg["provider"], tts.resolve_tts_api_key(cfg)), ("openai", "sk-proj-speech-key"))
        public = tts.public_tts_config(cfg)
        self.assertEqual(public["api_key"], "")
        self.assertTrue(public["api_key_set"])


if __name__ == "__main__":
    unittest.main()
