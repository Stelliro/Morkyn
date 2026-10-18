"""The packaged build: one root beside the exe, and the launcher's commands without an interpreter.

Run:  .venv\\Scripts\\python -m unittest tests.test_packaging_paths
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class OneRoot(unittest.TestCase):
    def test_a_checkout_roots_at_the_repo(self):
        from app import paths

        self.assertEqual(paths.app_root(), ROOT)

    def test_a_frozen_build_roots_beside_the_exe(self):
        from app import paths

        with mock.patch.object(sys, "frozen", True, create=True), mock.patch.object(sys, "executable", r"C:\Games\Morkyn\Morkyn.exe"):
            self.assertEqual(paths.app_root(), Path(r"C:\Games\Morkyn"))

    def test_every_module_takes_its_root_from_paths(self):
        import re

        offenders = []
        for path in (ROOT / "app").glob("*.py"):
            if path.name == "paths.py":
                continue
            text = path.read_text(encoding="utf-8")
            if re.search(r"^ROOT = Path\(__file__\)", text, re.M) or "Path(__file__).resolve().parent.parent /" in text:
                offenders.append(path.name)
        self.assertEqual(offenders, [], "use app.paths.ROOT so the packaged build finds its folders")


class ThePackagedUpdater(unittest.TestCase):
    def test_a_frozen_build_points_at_the_releases(self):
        from app import updates

        with mock.patch.object(sys, "frozen", True, create=True):
            status = updates.current_status()
        self.assertTrue(status.get("packaged"))
        self.assertIn("releases", status.get("release_url", ""))
        self.assertIn("packaged build", status.get("note", ""))

    def test_a_frozen_check_compares_the_running_version_to_the_newest_tag(self):
        from app import updates

        with mock.patch.object(sys, "frozen", True, create=True), \
                mock.patch.object(updates, "_latest_release", return_value={"tag": "v9.9.9", "url": "https://x/r"}), \
                mock.patch.object(updates, "_running_version", return_value="0.10.0-dev.14"), \
                mock.patch.object(updates, "_record_event"):
            result = updates.check_for_updates()
        self.assertTrue(result.get("update_available"))
        self.assertIn("9.9.9", result.get("message", ""))
        with mock.patch.object(sys, "frozen", True, create=True), \
                mock.patch.object(updates, "_latest_release", return_value={"tag": "v0.10.0-dev.14"}), \
                mock.patch.object(updates, "_running_version", return_value="0.10.0-dev.14"), \
                mock.patch.object(updates, "_record_event"):
            self.assertFalse(updates.check_for_updates().get("update_available"))


class LauncherCommands(unittest.TestCase):
    def test_a_checkout_uses_the_interpreter(self):
        from app import launcher

        self.assertEqual(launcher.module_command("app.model_limits", "--context", "m.gguf")[1:], ["-m", "app.model_limits", "--context", "m.gguf"])
        self.assertEqual(launcher.snippet_command("print(1)")[1:], ["-c", "print(1)"])
        self.assertEqual(launcher.server_command("127.0.0.1", 8000)[1:3], ["-m", "uvicorn"])

    def test_a_frozen_build_asks_the_exe(self):
        from app import launcher

        with mock.patch.object(sys, "frozen", True, create=True):
            self.assertEqual(launcher.module_command("llama_cpp.server", "--model", "m.gguf")[1:], ["--run-module", "llama_cpp.server", "--model", "m.gguf"])
            self.assertEqual(launcher.snippet_command("print(1)")[1:], ["--run-code", "print(1)"])
            self.assertEqual(launcher.server_command("127.0.0.1", 8000)[1:], ["--serve", "127.0.0.1", "8000"])

    def test_the_exe_entry_runs_a_module_and_a_snippet(self):
        import io
        from contextlib import redirect_stdout

        import morkyn_app

        out = io.StringIO()
        with redirect_stdout(out):
            code = morkyn_app.run_code("print(2 + 2)")
        self.assertEqual((code, out.getvalue().strip()), (0, "4"))
        out = io.StringIO()
        with redirect_stdout(out):
            code = morkyn_app.run_module("app.model_limits", ["--context"])
        self.assertEqual(code, 0)
        self.assertTrue(out.getvalue().strip().splitlines()[-1].isdigit(), out.getvalue())


if __name__ == "__main__":
    unittest.main()
