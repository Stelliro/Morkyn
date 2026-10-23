"""A launcher that finds an older server on its port replaces it instead of using it.

Linux .deb, 2026-10-23 (#147): closing the window left the launcher and server
running; the next open said "A Mørkyn server is already running on port 8000;
using it", and the speech engine installed since was never loaded. The server
reports the build and packs it booted with; the launcher compares them with
its own and closes a stale one.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import launcher, runtime_packs  # noqa: E402


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


_LISTENER = (
    "import socket, sys, time\n"
    "s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)\n"
    "s.bind(('127.0.0.1', int(sys.argv[1]))); s.listen()\n"
    "time.sleep(60)\n"
)


class TheStaleCheck(unittest.TestCase):
    def test_the_same_build_and_packs_is_not_stale(self):
        self.assertFalse(launcher.server_is_stale({"identity": runtime_packs.boot_identity()}))

    def test_another_build_or_no_identity_is_stale(self):
        other = dict(runtime_packs.boot_identity(), build="/opt/old/Morkyn:1:1")
        self.assertTrue(launcher.server_is_stale({"identity": other}))
        self.assertTrue(launcher.server_is_stale({}))

    def test_a_pack_installed_since_makes_the_server_stale(self):
        with tempfile.TemporaryDirectory() as runtime:
            with mock.patch.dict(os.environ, {"MORKYN_RUNTIME_DIR": runtime}):
                booted = runtime_packs.boot_identity()
                pack = Path(runtime) / "piper-speech"
                (pack / "site").mkdir(parents=True)
                (pack / "pack.json").write_text(json.dumps({"id": "piper-speech", "installed_at": "now"}), encoding="utf-8")
                self.assertTrue(launcher.server_is_stale({"identity": booted}))


@unittest.skipUnless(sys.platform.startswith("linux"), "process checks read /proc")
class ClosingTheStaleServer(unittest.TestCase):
    def _listen(self, *argv: str) -> tuple[subprocess.Popen, int]:
        port = _free_port()
        proc = subprocess.Popen([*argv, str(port)], stdin=subprocess.DEVNULL)
        deadline = time.monotonic() + 10
        while not launcher.port_open("127.0.0.1", port):
            self.assertLess(time.monotonic(), deadline, "the stand-in server never listened")
            time.sleep(0.05)
        self.addCleanup(lambda: (proc.kill(), proc.wait(timeout=10)))
        return proc, port

    def test_a_stale_morkyn_server_is_closed_and_the_port_freed(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "morkyn_app_stand_in.py"
            script.write_text(_LISTENER, encoding="utf-8")
            proc, port = self._listen(sys.executable, str(script))
            self.assertTrue(launcher.close_stale_server({"pid": proc.pid, "launcher_pid": None}, port, timeout=5))
            proc.wait(timeout=5)
            self.assertFalse(launcher.port_open("127.0.0.1", port))

    def test_a_process_that_is_not_morkyn_is_left_alone(self):
        proc, port = self._listen(sys.executable, "-c", _LISTENER)
        self.assertFalse(launcher.close_stale_server({"pid": proc.pid}, port, timeout=1))
        self.assertIsNone(proc.poll())


if __name__ == "__main__":
    unittest.main()
