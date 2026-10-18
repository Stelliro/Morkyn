"""8B run 148, T64: the clerk watching from the tally house doorway travelled with the player.

"I leave the Tally House and walk to the Reeve's Office at the Harbour to ask
Ulric ..." was answered with Griselda "watching from the doorway of the Tally
House"; MOVE "The Reeves' Office" against the stored "Reeves’ Office" read as a
place made this turn, and the people-named-after-arrival rule carried her to
the harbour, where she answered the next two turns in Ulric's place.

Run:  .venv\\Scripts\\python -m unittest tests.test_8b_run148_carry
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-run148-carry-"))
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


LINE = ("I leave the Tally House and walk to the Reeve's Office at the Harbour to ask Ulric what the Reeves want for the "
        "Stormbreaker's ledger.")
PROSE = (
    "You step out of the Tally House, the scent of ink and damp paper lingering in the morning breeze. You head toward "
    "The Harbour [[L90]], your boots crunching over the packed earth. The Reeves' Office is a modest building, its wooden "
    "frame weathered by the sea's relentless touch.\n\nGriselda Kemp [[B]] watches from the doorway of the Tally House, her "
    "expression tense. You don't stop to speak; your goal is the Reeves' Office.\n\nYou arrive at the Office. Inside, you "
    "notice a single figure seated at a desk. It is Ulric [[E]], and he is not alone."
)


def _world(office_name: str):
    from app import world
    from app.db import connect, init_db

    init_db()
    world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
    with connect() as conn:
        town = int(conn.execute("SELECT current_location_id FROM player").fetchone()[0])
        conn.execute("INSERT INTO locations (code, name, summary) VALUES ('L90', 'The Harbour', '')")
        harbour = int(conn.execute("SELECT id FROM locations WHERE code = 'L90'").fetchone()[0])
        conn.execute("INSERT INTO locations (code, name, summary, parent_id) VALUES ('L91', ?, '', ?)", (office_name, harbour))
        conn.execute("DELETE FROM npcs")
        conn.execute(
            "INSERT INTO npcs (code, location_id, name, race, role, summary, attitude) VALUES ('B', ?, 'Griselda Kemp', 'human', 'clerk', '', 'neutral')",
            (town,),
        )
    return town


class TheClerkStaysBehind(unittest.TestCase):
    def test_the_stored_spelling_is_the_destination(self):
        from app import world
        from app.db import connect

        _world("Reeves’ Office")
        result = {"player": {"move_to_location": "The Reeves' Office"}}
        with connect() as conn:
            world._place_new_people_at_arrival(conn, [], result, LINE, PROSE)
        self.assertNotIn("Griselda Kemp", result.get("_arrive_with_player") or [])

    def test_watching_from_the_doorway_is_staying(self):
        from app import world
        from app.db import connect

        _world("Harbour Watch House")
        result = {"player": {"move_to_location": "The Reeves' Office"}}
        with connect() as conn:
            world._place_new_people_at_arrival(conn, [], result, LINE, PROSE)
        self.assertNotIn("Griselda Kemp", result.get("_arrive_with_player") or [])

    def test_someone_shown_at_the_new_place_still_comes(self):
        from app import world
        from app.db import connect

        _world("Harbour Watch House")
        prose = ("You walk to the Reeves' Office. At the Office door Griselda Kemp [[B]] is already waiting for you, ledger "
                 "under her arm. \"You took your time,\" she says.")
        result = {"player": {"move_to_location": "The Reeves' Office"}}
        with connect() as conn:
            world._place_new_people_at_arrival(conn, [], result, LINE, prose)
        self.assertIn("Griselda Kemp", result.get("_arrive_with_player") or [])

    def test_the_stay_shapes(self):
        from app.world import _stays_behind

        self.assertTrue(_stays_behind("Eldric watches you go from the bar.", "Eldric"))
        self.assertTrue(_stays_behind("Behind you, Aldous turns back to his work.", "Aldous"))
        self.assertFalse(_stays_behind("Aldous falls in beside you on the path.", "Aldous"))


class ReportingAtAnotherPlaceGoesThere(unittest.TestCase):
    """T74: "I report to Ulric at the Reeves' Office ..." kept the player at the wreck; the MOVE was dropped as unasked."""

    LINE = ("I report to Ulric at the Reeves' Office that the Stormbreaker's hull is shored and lashed, and ask what the "
            "Reeves pay for it.")
    PROSE = ("You report to Ulric [[E]] at The Reeves' Office [[L91]] that The Stormbreaker's Wreck is secured, its timbers "
             "shored and lashed. The man leans on a desk, his fingers tapping a rhythm on the worn surface. \"Reeves pay for "
             "salvage,\" he says, \"but the wreck is not yours to sell.\"")

    def test_the_line_acts_at_the_office(self):
        from app import world

        rows = [{"name": "The Reeve's Office", "code": "L7"}, {"name": "The Stormbreaker's Wreck", "code": "L8"}]
        self.assertTrue(world._acts_at_known_place(self.LINE, rows, "The Stormbreaker's Wreck"))
        self.assertFalse(world._acts_at_known_place("I search the hull at the wreck for anything left.", rows, "The Stormbreaker's Wreck"))
        self.assertFalse(world._acts_at_known_place("I ask who is at the Reeve's Office these days.", rows, "The Stormbreaker's Wreck"))

    def test_the_move_to_the_office_stands(self):
        from app import world
        from app.db import connect

        _world("The Reeve's Office")
        with connect() as conn:
            harbour = int(conn.execute("SELECT id FROM locations WHERE code = 'L90'").fetchone()[0])
            conn.execute("INSERT INTO locations (code, name, summary, parent_id) VALUES ('L92', \"The Stormbreaker's Wreck\", '', ?)", (harbour,))
            wreck = int(conn.execute("SELECT id FROM locations WHERE code = 'L92'").fetchone()[0])
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (wreck,))
            result = {"narration": self.PROSE, "player": {"move_to_location": "Reeves’ Office"}}
            report = world.resolve_movement(conn, result, self.LINE, intent="conversation", narration=self.PROSE)
        self.assertNotIn(report.get("status"), {"dropped_unshown", "dropped"}, report)
        self.assertTrue(result["player"].get("move_to_location") or result["player"].get("move_to_location_code"), report)


class OpenGroundHasNoDoor(unittest.TestCase):
    """T79: the walk to the wreck under the harbour ended on the quay ("entered from The Harbour; the journey ends there")."""

    def test_the_wreck_is_reached_by_the_walk(self):
        from app import world
        from app.db import connect

        town = _world("The Reeve's Office")
        with connect() as conn:
            harbour = int(conn.execute("SELECT id FROM locations WHERE code = 'L90'").fetchone()[0])
            conn.execute("INSERT INTO locations (code, name, summary, parent_id) VALUES ('L92', \"The Stormbreaker's Wreck\", '', ?)", (harbour,))
            wreck = world._location_row(conn, int(conn.execute("SELECT id FROM locations WHERE code = 'L92'").fetchone()[0]))
            office = world._location_row(conn, int(conn.execute("SELECT id FROM locations WHERE code = 'L91'").fetchone()[0]))
            self.assertTrue(world.venue_entry_check(conn, town, wreck)["ok"])
            # A building under the harbour still has its door.
            self.assertEqual(world.venue_entry_check(conn, town, office).get("reason"), "unreachable")


class TheOfficeUnderAnotherSpelling(unittest.TestCase):
    """T66: "go into the Reeves' Office" made a third office beside "The Reeve's Office" and "Reeves’ Office"."""

    def test_the_known_office_is_the_one_entered(self):
        from app import world
        from app.db import connect

        _world("The Reeve's Office")
        line = "I turn from Griselda and go into the Reeves' Office to find Ulric at his desk."
        prose = ("You turn from Griselda and slip through the doors of the Reeves’ Office, the wood creaking under your weight. "
                 "At the far end, behind a heavy oak table, sits Ulric.")
        with connect() as conn:
            harbour = int(conn.execute("SELECT id FROM locations WHERE code = 'L90'").fetchone()[0])
            before = int(conn.execute("SELECT COUNT(*) FROM locations").fetchone()[0])
            name = world._civic_building_requested(conn, harbour, line, prose)
            after = int(conn.execute("SELECT COUNT(*) FROM locations").fetchone()[0])
        self.assertEqual(name, "The Reeve's Office")
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
