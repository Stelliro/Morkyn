"""Versions: a release installed from an archive, the active choice, and the handover decision.

Run:  .venv\\Scripts\\python -m unittest tests.test_versions
"""
from __future__ import annotations

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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-versions-"))
_ENV = {**isolated_data_env(str(_TMP)), "MORKYN_VERSIONS_DIR": str(_TMP / "versions")}
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


def _fake_build_zip(path: Path) -> Path:
    exe = "Morkyn/Morkyn.exe" if os.name == "nt" else "Morkyn/Morkyn"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(exe, "not really an executable")
        zf.writestr("Morkyn/README-package.md", "fake build")
    return path


class AnInstalledVersion(unittest.TestCase):
    def test_install_from_an_archive_then_choose_and_remove(self):
        from app import versions as v

        archive = _fake_build_zip(_TMP / "Morkyn-0.10.0-dev.99-windows-x64.zip")
        with mock.patch.object(v, "active_file", return_value=_TMP / "active.json"):
            result = v.install("v0.10.0-dev.99", archive.as_uri(), wait=True)
            self.assertTrue(result["ok"], result)
            self.assertEqual(v.installed_versions(), ["0.10.0-dev.99"])
            self.assertIsNotNone(v.exe_path("0.10.0-dev.99"))
            self.assertFalse(v.set_active("0.10.0-dev.98")["ok"])
            self.assertTrue(v.set_active("0.10.0-dev.99")["ok"])
            self.assertEqual(v.active_tag(), "0.10.0-dev.99")
            listing = v.list_releases(check_online=False)
            self.assertEqual([r["tag"] for r in listing["releases"] if r["installed"]], ["0.10.0-dev.99"])
            self.assertTrue(v.remove("0.10.0-dev.99")["ok"])
            self.assertEqual(v.active_tag(), "")

    def test_the_platform_archive_is_recognised(self):
        from app import versions as v

        with mock.patch.object(sys, "platform", "win32"):
            self.assertTrue(v.archive_matches("Morkyn-0.10.0-dev.14-windows-x64.zip"))
            self.assertFalse(v.archive_matches("Morkyn-0.10.0-dev.14-macos.zip"))
            self.assertFalse(v.archive_matches("morkyn-pack-llama-cpp-cuda-windows-x64-cp312.zip"))
        with mock.patch.object(sys, "platform", "linux"):
            self.assertTrue(v.archive_matches("Morkyn-0.10.0-dev.14-linux-x86_64.tar.gz"))


class TheHandover(unittest.TestCase):
    def test_a_checkout_never_hands_over(self):
        from app import versions as v

        self.assertIsNone(v.handover_target())
        self.assertIsNone(v.hand_over([]))

    def test_a_frozen_build_hands_over_to_the_chosen_version_only(self):
        from app import versions as v

        archive = _fake_build_zip(_TMP / "Morkyn-0.10.0-dev.97-windows-x64.zip")
        with mock.patch.object(v, "active_file", return_value=_TMP / "active2.json"):
            self.assertTrue(v.install("0.10.0-dev.97", archive.as_uri(), wait=True)["ok"])
            v.set_active("0.10.0-dev.97")
            with mock.patch.object(sys, "frozen", True, create=True), mock.patch.object(v, "running_version", return_value="0.10.0-dev.14"):
                self.assertEqual(v.handover_target(), v.exe_path("0.10.0-dev.97"))
            with mock.patch.object(sys, "frozen", True, create=True), mock.patch.object(v, "running_version", return_value="0.10.0-dev.97"):
                self.assertIsNone(v.handover_target())  # already the chosen one
            with mock.patch.object(sys, "frozen", True, create=True), mock.patch.dict(os.environ, {"MORKYN_NO_HANDOVER": "1"}):
                self.assertIsNone(v.handover_target())
            v.remove("0.10.0-dev.97")

    def test_a_target_that_dies_at_once_is_dropped(self):
        from app import versions as v

        with mock.patch.object(v, "active_file", return_value=_TMP / "active3.json"), \
                mock.patch.object(v, "handover_target", return_value=_TMP / "nope.exe"), \
                mock.patch.object(v, "set_active") as cleared:
            self.assertIsNone(v.hand_over([]))
            cleared.assert_called_once_with("")


if __name__ == "__main__":
    unittest.main()
