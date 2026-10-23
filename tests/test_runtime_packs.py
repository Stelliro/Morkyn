"""Runtime packs: the engine choice, a pack installed from a zip, a custom build, the hardware pick.

Run:  .venv\\Scripts\\python -m unittest tests.test_runtime_packs
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-packs-"))
_ENV = {**isolated_data_env(str(_TMP)), "MORKYN_RUNTIME_DIR": str(_TMP / "runtime")}
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


def _fake_pack_zip(path: Path, pack_id: str) -> Path:
    from app.runtime_packs import arch_tag, os_tag, python_tag

    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("pack.json", json.dumps({"id": pack_id, "version": "0.0.1", "python_tag": python_tag(), "os": os_tag(), "arch": arch_tag()}))
        zf.writestr("site/fake_engine_module/__init__.py", "ENGINE = 'fake'\n")
    return path


class TheChoice(unittest.TestCase):
    def test_auto_follows_the_hardware(self):
        from app import runtime_packs as rp

        with mock.patch("app.hardware.recommended_pack", return_value=("llama-cpp-cpu", "test")):
            picked = rp.choice()
        self.assertEqual((picked["mode"], picked["pack"]), ("auto", "llama-cpp-cpu"))

    def test_a_pack_and_none_are_kept_and_a_bad_value_is_auto(self):
        from app.launcher_prefs import normalize_prefs

        self.assertEqual(normalize_prefs({"engine_pack": "llama-cpp-cpu"})["engine_pack"], "llama-cpp-cpu")
        self.assertEqual(normalize_prefs({"engine_pack": "none"})["engine_pack"], "none")
        self.assertEqual(normalize_prefs({"engine_pack": "rocm-please"})["engine_pack"], "auto")

    def test_custom_needs_an_existing_path(self):
        from app import runtime_packs as rp

        self.assertFalse(rp.set_choice("custom", str(_TMP / "nowhere"))["ok"])
        folder = _TMP / "my-engine"
        folder.mkdir(exist_ok=True)
        result = rp.set_choice("custom", str(folder))
        self.assertTrue(result["ok"], result)
        self.assertEqual(rp.choice()["mode"], "custom")
        rp.set_choice("auto")


class APackFromAZip(unittest.TestCase):
    def test_install_unpacks_and_activates(self):
        from app import runtime_packs as rp

        zip_path = _fake_pack_zip(_TMP / "pack.zip", "llama-cpp-cpu")
        rp.set_choice("llama-cpp-cpu")
        try:
            result = rp.install("llama-cpp-cpu", zip_path.as_uri(), wait=True)
            self.assertTrue(result["ok"], result)
            self.assertEqual([p["id"] for p in rp.installed()], ["llama-cpp-cpu"])
            site = str(rp.packs_dir() / "llama-cpp-cpu" / "site")
            self.assertIn(site, sys.path)
            self.assertTrue(rp.provides("fake_engine_module"))
            self.assertTrue(rp.remove("llama-cpp-cpu")["ok"])
            self.assertEqual(rp.installed(), [])
        finally:
            rp.set_choice("auto")
            sys.modules.pop("fake_engine_module", None)

    def test_a_zip_that_is_no_pack_is_refused(self):
        from app import runtime_packs as rp

        bad = _TMP / "bad.zip"
        with zipfile.ZipFile(bad, "w") as zf:
            zf.writestr("readme.txt", "no")
        result = rp.install("llama-cpp-cpu", bad.as_uri(), wait=True)
        self.assertFalse(result["ok"])
        self.assertIn("not a", result.get("error", ""))

    def test_auto_install_is_a_checkouts_no_op(self):
        from app import runtime_packs as rp

        self.assertEqual(rp.auto_install_if_needed().get("skipped"), "not packaged")


class TheSpeechAddOn(unittest.TestCase):
    """Stell, 2026-10-22: "install local speech engine" in the exe opened a second Mørkyn."""

    def test_an_installed_addon_is_on_the_path_whatever_engine_is_chosen(self):
        from app import runtime_packs as rp

        zip_path = _fake_pack_zip(_TMP / "piper.zip", "piper-speech")
        rp.set_choice("none")
        try:
            self.assertTrue(rp.install("piper-speech", zip_path.as_uri(), wait=True)["ok"])
            sys.path[:] = [p for p in sys.path if "piper-speech" not in p]
            rp.activate()
            self.assertTrue(any(p.endswith(str(Path("piper-speech") / "site")) for p in sys.path))
            self.assertTrue(rp.remove("piper-speech")["ok"])
        finally:
            rp.set_choice("auto")
            sys.modules.pop("fake_engine_module", None)

    def test_the_exe_installs_the_speech_pack_not_pip(self):
        from app import tts

        from app import runtime_packs

        offered = {runtime_packs.asset_name("piper-speech"): {"url": "x", "size": 1}}
        with mock.patch.object(sys, "frozen", True, create=True), \
                mock.patch("app.runtime_packs.available_assets", return_value=offered), \
                mock.patch("app.runtime_packs.install", return_value={"ok": True}) as install, \
                mock.patch.object(tts, "piper_installed", return_value=(True, "1.8.0")), \
                mock.patch("subprocess.run") as run:
            out = tts.pip_install_piper()
        self.assertTrue(out["ok"], out)
        install.assert_called_once()
        self.assertEqual(install.call_args[0][0], "piper-speech")
        run.assert_not_called()

    def test_the_llama_server_starts_through_the_exes_module_runner(self):
        from app.launcher import module_command

        with mock.patch.object(sys, "frozen", True, create=True):
            self.assertEqual(module_command("llama_cpp.server")[1:3], ["--run-module", "llama_cpp.server"])
        source = (ROOT / "app" / "llm.py").read_text(encoding="utf-8")
        self.assertIn('module_command("llama_cpp.server")', source)
        self.assertNotIn('"-m",\n        "llama_cpp.server"', source)


class ACustomZip(unittest.TestCase):
    def test_the_custom_zip_is_unpacked_and_put_on_the_path(self):
        from app import runtime_packs as rp

        zip_path = _fake_pack_zip(_TMP / "custom.zip", "custom")
        rp.set_choice("custom", str(zip_path))
        try:
            added = rp.activate()
            self.assertTrue(any(a.endswith("site") for a in added), added)
        finally:
            rp.set_choice("auto")


class TheHardwarePick(unittest.TestCase):
    def test_vendors_map_to_packs(self):
        from app import hardware

        with mock.patch.object(sys, "platform", "win32"):
            self.assertEqual(hardware.recommended_pack([{"vendor": "nvidia", "name": "RTX"}])[0], "llama-cpp-cuda")
            self.assertEqual(hardware.recommended_pack([{"vendor": "amd", "name": "Radeon"}])[0], "llama-cpp-vulkan")
            self.assertEqual(hardware.recommended_pack([])[0], "llama-cpp-cpu")
        with mock.patch.object(sys, "platform", "darwin"):
            self.assertEqual(hardware.recommended_pack([{"vendor": "apple", "name": "M2"}])[0], "llama-cpp-metal")

    def test_detection_never_raises(self):
        from app import hardware

        summary = hardware.summary()
        self.assertIn(summary["recommended"], {"llama-cpp-cuda", "llama-cpp-cpu", "llama-cpp-metal", "llama-cpp-vulkan"})


if __name__ == "__main__":
    unittest.main()
