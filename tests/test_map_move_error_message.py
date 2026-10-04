"""The map-move 409 hint reaches the player, not "[object Object]".

`/api/tiles/map/move` answers confinement and exhaustion with an object in
`detail` (`message`, `reasons`, ...). Both browser readers built
`new Error(data.detail || ...)`, so the banner and the alert showed
"[object Object]" instead of the hint the server wrote.

Run:  python -m unittest tests.test_map_move_error_message
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_JS = ROOT / "static" / "app.js"


def _helper_source() -> str:
    text = APP_JS.read_text(encoding="utf-8")
    match = re.search(r"^function apiErrorMessage\(data, status\) \{\n.*?^\}\n", text, re.M | re.S)
    assert match, "apiErrorMessage helper missing from static/app.js"
    return match.group(0)


class TestMapMoveReadersUseTheHelper(unittest.TestCase):
    def test_both_map_move_fetches_read_detail_through_the_helper(self):
        text = APP_JS.read_text(encoding="utf-8")
        blocks = [m.start() for m in re.finditer(r'fetch\("/api/tiles/map/move"', text)]
        self.assertEqual(len(blocks), 2)
        for start in blocks:
            window = text[start : start + 900]
            self.assertIn("apiErrorMessage(data, res.status)", window)
            self.assertNotIn("new Error(data.detail ||", window)

    def test_helper_is_a_top_level_function(self):
        self.assertIsNotNone(_helper_source())


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class TestHelperInNode(unittest.TestCase):
    def _run(self, data, status=409) -> str:
        script = (
            _helper_source()
            + "\nprocess.stdout.write(apiErrorMessage("
            + json.dumps(data)
            + ", "
            + str(status)
            + "));\n"
        )
        done = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout

    def test_object_detail_shows_its_message(self):
        hint = "Too exhausted to travel; wait, meditate, or sleep to recover energy."
        out = self._run({"detail": {"message": hint, "reasons": ["insufficient_energy"]}})
        self.assertEqual(out, hint)
        self.assertNotIn("[object Object]", out)

    def test_string_detail_still_works(self):
        self.assertEqual(self._run({"detail": "No active map."}, 400), "No active map.")

    def test_error_key_and_status_fallbacks(self):
        self.assertEqual(self._run({"error": "blocked"}), "blocked")
        self.assertEqual(self._run({}, 503), "HTTP 503")
        self.assertEqual(self._run({"detail": {"reasons": ["x"]}}, 409), "HTTP 409")


if __name__ == "__main__":
    unittest.main()
