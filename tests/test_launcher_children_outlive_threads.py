"""A server the launcher starts from a short-lived thread keeps running.

The launcher ties its children to itself on Linux with PR_SET_PDEATHSIG, which
fires when the *thread* that forked the child exits. The window starts the
server from the morkyn-start thread; it ended a moment after the server was
ready, the server got SIGTERM, and the first Linux window showed "127.0.0.1
refused to connect" (Stell, 2026-10-23). app.launcher._spawn forks every child
from one long-lived thread.
"""
from __future__ import annotations

import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import launcher  # noqa: E402


@unittest.skipUnless(sys.platform.startswith("linux"), "PR_SET_PDEATHSIG is Linux only")
class ChildrenOutliveTheirThread(unittest.TestCase):
    def test_a_child_started_from_a_thread_that_ends_keeps_running(self):
        box: dict[str, subprocess.Popen] = {}

        def start() -> None:
            box["proc"] = launcher._spawn(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        thread = threading.Thread(target=start, name="short-lived")
        thread.start()
        thread.join()
        proc = box["proc"]
        try:
            time.sleep(1.0)
            self.assertIsNone(proc.poll(), "the child died with the thread that started it")
        finally:
            proc.kill()
            proc.wait(timeout=10)

    def test_both_children_go_through_the_spawner(self):
        source = (ROOT / "app" / "launcher.py").read_text(encoding="utf-8")
        body = source[source.index("class Supervisor") :]
        self.assertNotIn("subprocess.Popen(", body)
        self.assertGreaterEqual(body.count("_spawn("), 2)


if __name__ == "__main__":
    unittest.main()
