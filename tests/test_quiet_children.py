"""app/quiet_children.py: tools the app runs open no console windows on Windows.

The window starts the server without a console, so without this guard every
nvidia-smi call (one per model call, via app/gpu_gate.py) flashed a terminal
window open; with the narration pipeline on, many per turn.
"""
from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app  # noqa: E402,F401  (importing the package installs the guard)
from app import quiet_children  # noqa: E402
from app.quiet_children import CREATE_NEW_CONSOLE, CREATE_NO_WINDOW, DETACHED_PROCESS, quiet_flags  # noqa: E402


class FlagTests(unittest.TestCase):
    def test_no_choice_means_no_window(self):
        self.assertEqual(quiet_flags(0), CREATE_NO_WINDOW)
        self.assertEqual(quiet_flags(None), CREATE_NO_WINDOW)

    def test_other_flags_are_kept(self):
        new_group = 0x00000200
        self.assertEqual(quiet_flags(new_group), new_group | CREATE_NO_WINDOW)

    def test_an_explicit_console_choice_wins(self):
        self.assertEqual(quiet_flags(CREATE_NEW_CONSOLE), CREATE_NEW_CONSOLE)
        self.assertEqual(quiet_flags(DETACHED_PROCESS), DETACHED_PROCESS)


@unittest.skipUnless(os.name == "nt", "console windows are a Windows concern")
class InstalledGuardTests(unittest.TestCase):
    def test_importing_app_installs_it(self):
        self.assertTrue(getattr(subprocess.Popen, "_morkyn_quiet", False))
        self.assertTrue(quiet_children.install(), "a second install must be a no-op that reports active")

    def test_a_plain_run_is_started_without_a_window(self):
        seen = {}
        real = subprocess.Popen._execute_child

        def spy(self, *args):
            # _execute_child(args, executable, preexec_fn, close_fds, pass_fds, cwd, env, startupinfo, creationflags, ...)
            seen["flags"] = args[8]
            return real(self, *args)

        with mock.patch.object(subprocess.Popen, "_execute_child", spy):
            out = subprocess.run([sys.executable, "-c", "print('ok')"], capture_output=True, text=True, timeout=30)
        self.assertEqual(out.stdout.strip(), "ok", "output must still come back")
        self.assertTrue(seen["flags"] & CREATE_NO_WINDOW)


if __name__ == "__main__":
    unittest.main()
