"""7B run 10 (Qwen2.5 7B on MLE, agent as player): coin placed in the hand, things set back."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-7b-run10-"))
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


class CoinPlacedInTheHand(unittest.TestCase):
    """T7: "She places a handful of polished coins in your palm" moved no gold."""

    def test_reader(self):
        from app.prose_state import coin_handed_to_player as read

        self.assertIsNotNone(read("She places a handful of polished coins in your palm."))
        self.assertIsNotNone(read("She puts the coin into your outstretched hand."))
        self.assertIsNone(read("You place three coins in her hand."))
        self.assertIsNone(read("He sets a small stack of coins on the counter."))


class SetBackIsAGive(unittest.TestCase):
    """T6: "I set the knives back on her bench" left them in the pack."""

    def test_patterns(self):
        from app.world import _LINE_GIVE_RE, _PROSE_GIVE_RE

        self.assertTrue(_LINE_GIVE_RE.search("I set the knives back on her bench."))
        self.assertTrue(_PROSE_GIVE_RE.search("You set the sharpened blades back on Jehane's bench."))
        self.assertTrue(_LINE_GIVE_RE.search("I return the lantern to Mira."))
        # Setting a thing down to ask its price is not giving it (run 5 T41).
        self.assertFalse(_LINE_GIVE_RE.search("I set the fitting on the counter and ask what it's worth."))

    def test_through_the_reconcile(self):
        from app import world
        from app.db import connect, init_db

        init_db()
        with connect() as conn:
            conn.execute("DELETE FROM inventory")
            conn.execute("INSERT INTO inventory (name, quantity) VALUES ('sharpened blade', 5)")
            removed = world._remove_shown_gives(
                conn,
                [],
                "You set the sharpened blades back on Jehane's bench, giving them a final glance.",
                "I set the blades back on her bench. \"These are yours, not mine.\"",
            )
        self.assertTrue(removed, removed)


if __name__ == "__main__":
    unittest.main()
