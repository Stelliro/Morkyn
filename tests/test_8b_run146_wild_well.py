"""8B run 146, T56: a well in a clearing in the woods is not a venue.

"I put the vial back where it lay and walk to the well" at "The clearing"
(a wild place reached along a stream) opened a venue "The clearing Well" and
moved the player into it. Venues open in settlements; a feature of a wild
place is a thing in that place, and the player stays put.

Run:  .venv\\Scripts\\python -m unittest tests.test_8b_run146_wild_well
"""
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-run146-well-"))
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


LINE = "I put the vial back where it lay and walk to the well. I lower the bucket on its rope, draw it up, and taste the water."
PROSE = ("The vial is returned to its resting place, a small stone ledge beside the well. You walk toward the well, the "
         "morning light catching on the wooden bucket as you lower it on its rope. The taste is sharp, a hint of salt.")


class AWellInTheWoodsIsNoVenue(unittest.TestCase):
    def test_no_venue_opens_in_a_clearing(self):
        from app import world
        from app.db import connect, init_db

        init_db()
        world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
        with connect() as conn:
            clearing = world._upsert_location(conn, "The clearing", "A narrow strip of cleared ground by a stream.")
            self.assertEqual(world._mint_venue_from_request(conn, int(clearing), LINE, PROSE), "")
            self.assertEqual(world._venue_requested_and_reached(conn, LINE, PROSE, "L%d" % int(clearing)), "")
            conn.rollback()

    def test_a_town_well_still_opens(self):
        from app import world
        from app.db import connect, init_db

        init_db()
        world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
        with connect() as conn:
            town = int(conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()[0])
            name = world._mint_venue_from_request(conn, town, "I walk to the well in the square and draw a bucket.", PROSE)
            self.assertTrue(name, "a town well is a venue of the town")
            conn.rollback()


if __name__ == "__main__":
    unittest.main()
