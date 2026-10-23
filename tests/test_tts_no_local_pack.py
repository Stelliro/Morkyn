"""The packaged game says plainly when the local speech pack is not published (#146).

Piper and the espeak-ng inside it are GPL-3.0, so the speech pack is not on the
release (Stell, 2026-10-23). Install used to fail with "no
morkyn-pack-piper-speech-...zip on the runtime-packs release yet".
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import runtime_packs, tts  # noqa: E402


class NoLocalPack(unittest.TestCase):
    def test_a_release_without_the_pack_names_the_online_providers(self):
        others = {runtime_packs.asset_name("llama-cpp-cuda"): {"url": "x", "size": 1}}
        with mock.patch.object(sys, "frozen", True, create=True), \
                mock.patch.object(runtime_packs, "available_assets", return_value=others), \
                mock.patch.object(runtime_packs, "install") as install:
            result = tts.pip_install_piper()
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], tts.MSG_NO_LOCAL_PACK)
        self.assertIn("ElevenLabs", result["error"])
        install.assert_not_called()

    def test_offline_still_tries_the_download(self):
        with mock.patch.object(sys, "frozen", True, create=True), \
                mock.patch.object(runtime_packs, "available_assets", return_value={}), \
                mock.patch.object(runtime_packs, "install", return_value={"ok": False, "error": "offline"}) as install:
            result = tts.pip_install_piper()
        install.assert_called_once()
        self.assertEqual(result["error"], "offline")


if __name__ == "__main__":
    unittest.main()
