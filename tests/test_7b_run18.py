"""7B run 18 (Qwen2.5 7B on MLE, agent as player): a venue the player names keeps that name."""
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-7b-run18-"))
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


class NamedVenue(unittest.TestCase):
    """T3: "I push open the door of Pollard's Cookshop" opened "Saltmarrow Diner"."""

    def test_keeps_the_players_name(self):
        from app import world
        from app.db import connect, init_db

        init_db()
        world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
        with connect() as conn:
            here = conn.execute("SELECT current_location_id FROM player").fetchone()[0]
            made = world._mint_venue_from_request(
                conn, here, "\"Ready.\" I push open the door of Pollard's Cookshop and go in.", "You step inside."
            )
        self.assertEqual(made, "Pollard's Cookshop")


if __name__ == "__main__":
    unittest.main()
