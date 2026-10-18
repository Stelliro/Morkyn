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


class AVenueSeenIsNotEntered(unittest.TestCase):
    """8B run 149, T14: "open the far door and step through" moved the player to the mill the prose only led toward."""

    LINE = "I open the far door and step through into whatever lies beyond."
    PROSE = ("The farthest gate creaks open as you step through. The Dredges stretch before you, a labyrinth of rusted pipes. "
             "A narrow path winds through the wreckage, leading toward the mill’s shadow. A figure stands at the edge of the "
             "mill, wrapped in a tattered cloak.")

    def _town_with_mill(self):
        from app.db import connect

        town = _world("The Reeve's Office")
        with connect() as conn:
            conn.execute("INSERT INTO locations (code, name, summary, parent_id, kind) VALUES ('L93', 'Velvet Ferret Mill', '', ?, 'mill')", (town,))
        return town

    def test_a_mill_led_toward_is_not_entered(self):
        from app import world
        from app.db import connect

        town = self._town_with_mill()
        with connect() as conn:
            self.assertIsNone(world._venue_named_in(conn, town, self.LINE, self.PROSE))

    def test_a_mill_the_prose_goes_into_is(self):
        from app import world
        from app.db import connect

        town = self._town_with_mill()
        prose = "You push through the mill's door. Inside, the Velvet Ferret Mill is dim and smells of wet grain."
        with connect() as conn:
            row = world._venue_named_in(conn, town, self.LINE, prose)
        self.assertIsNotNone(row)
        self.assertEqual(str(row["name"]), "Velvet Ferret Mill")

    def test_a_mill_the_line_names_is(self):
        from app import world
        from app.db import connect

        town = self._town_with_mill()
        with connect() as conn:
            row = world._venue_named_in(conn, town, "I go into the mill.", "You walk over. The miller looks up.")
        self.assertIsNotNone(row)


class TalkedToButShownElsewhere(unittest.TestCase):
    """8B run 149, T17: "Hugh Fairweather [[G]] stands at the edge of the Velvet Ferret Mill [[L2]]" moved Hugh to the tally house."""

    def test_hugh_stays_at_the_mill(self):
        from app import world
        from app.db import connect

        town = _world("The Reeve's Office")
        with connect() as conn:
            conn.execute("INSERT INTO locations (code, name, summary, parent_id, kind) VALUES ('L93', 'Velvet Ferret Mill', '', ?, 'mill')", (town,))
            mill = int(conn.execute("SELECT id FROM locations WHERE code = 'L93'").fetchone()[0])
            conn.execute(
                "INSERT INTO npcs (code, location_id, name, race, role, summary, attitude) VALUES ('G', ?, 'Hugh Fairweather', 'human', 'lock keeper', '', 'neutral')",
                (mill,),
            )
            prose = ("You ask. Lettice Garner [[B]] listens from the shadows. Hugh Fairweather [[G]], wrapped in a tattered cloak, "
                     "stands at the edge of the Velvet Ferret Mill [[L93]], his face obscured by a scarf.")
            result = {"narration": prose, "conversations": [{"npc_code": "G"}], "player": {}}
            world._place_talked_to_in_scene(conn, [], result)
            now = int(conn.execute("SELECT location_id FROM npcs WHERE code = 'G'").fetchone()[0])
        self.assertEqual(now, mill)

    def test_someone_shown_here_comes(self):
        from app import world
        from app.db import connect

        town = _world("The Reeve's Office")
        with connect() as conn:
            conn.execute("INSERT INTO locations (code, name, summary, parent_id, kind) VALUES ('L93', 'Velvet Ferret Mill', '', ?, 'mill')", (town,))
            mill = int(conn.execute("SELECT id FROM locations WHERE code = 'L93'").fetchone()[0])
            conn.execute(
                "INSERT INTO npcs (code, location_id, name, race, role, summary, attitude) VALUES ('G', ?, 'Hugh Fairweather', 'human', 'lock keeper', '', 'neutral')",
                (mill,),
            )
            prose = "Hugh Fairweather [[G]] steps out from behind the counter and sets a lock on the ledger. \"Ask,\" he says."
            result = {"narration": prose, "conversations": [{"npc_code": "G"}], "player": {}}
            world._place_talked_to_in_scene(conn, [], result)
            now = int(conn.execute("SELECT location_id FROM npcs WHERE code = 'G'").fetchone()[0])
        self.assertEqual(now, town)


class OutOfHidingIsNoExit(unittest.TestCase):
    """8B run 149, T88: "I step out from behind the crates with my hands open" walked the player out of the Dredges to the town square."""

    def test_stepping_out_from_behind_the_crates_leaves_nothing(self):
        from app.world import venue_move_intent

        self.assertEqual(venue_move_intent("I step out from behind the crates with my hands open."), "")
        self.assertEqual(venue_move_intent("I step out of the shadows with my hands open."), "")

    def test_stepping_out_of_the_inn_still_leaves(self):
        from app.world import venue_move_intent

        self.assertEqual(venue_move_intent("I step out of the inn."), "exit")


class ComeWithMeIsGoing(unittest.TestCase):
    """8B run 149, T94: '"Katerine, Ulric: come with me to the Tally House"' kept the player in the square while the prose sat inside."""

    LINE = "\"Then we find out together. Katerine, Ulric: come with me to the Tally House and we'll put the ledgers side by side.\""
    PROSE = ("You step between Katerine and Ulric, your words sharp as a blade. The two of them exchange a glance, then nod. "
             "Ulric tucks his tools into a satchel and follows you. Inside the Tally House, the room is dim, the flickering of a "
             "single lantern casting long shadows across the worn wooden tables. You pull out a stack of ledgers and lay them beside Katerine’s.")

    def test_the_invitation_asks_to_go(self):
        from app import world

        rows = [{"name": "Tally House", "code": "L6"}, {"name": "Saltmarrow", "code": "L1"}]
        self.assertTrue(world._invites_to_place(self.LINE, rows, "Saltmarrow"))
        self.assertFalse(world._invites_to_place("\"Come with me to the end of the world,\" she laughs.", rows, "Saltmarrow"))

    def test_the_move_to_the_tally_house_stands(self):
        from app import world
        from app.db import connect

        town = _world("The Reeve's Office")
        with connect() as conn:
            conn.execute("INSERT INTO locations (code, name, summary, parent_id) VALUES ('L94', 'Tally House', '', ?)", (town,))
            result = {"narration": self.PROSE, "player": {"move_to_location": "Tally House"}}
            report = world.resolve_movement(conn, result, self.LINE, intent="conversation", narration=self.PROSE)
        self.assertNotIn(report.get("status"), {"dropped_unshown", "dropped"}, report)


class RecalledIsNotShown(unittest.TestCase):
    """8B run 150, T6: "Mabel's words linger in your mind" after the walk to the dock carried Mabel from the tally house to the dock."""

    LINE = "I go down to the dock to find the reeve and ask his price for the boat to the east reef."

    def _dock(self):
        from app.db import connect

        town = _world("The Reeve's Office")
        with connect() as conn:
            conn.execute("INSERT INTO locations (code, name, summary, parent_id) VALUES ('L95', 'The Dock', '', ?)", (town,))
            conn.execute("UPDATE npcs SET name = 'Mabel', code = 'A' WHERE code = 'B'")
        return town

    def test_her_words_recalled_leave_her_at_the_tally_house(self):
        from app import world
        from app.db import connect

        town = self._dock()
        prose = ("You step out of the tally house and onto the dock. Mabel [[A]]’s words linger in your mind—the reeve’s got a "
                 "boat tied up at the dock. You find the reeve standing by a small boat, his arms crossed.")
        with connect() as conn:
            world._place_new_people_at_arrival(conn, [], {"player": {"move_to_location": "The Dock"}}, self.LINE, prose)
            now = int(conn.execute("SELECT location_id FROM npcs WHERE code = 'A'").fetchone()[0])
        self.assertEqual(now, town)

    def test_her_standing_there_brings_her(self):
        from app import world
        from app.db import connect

        self._dock()
        prose = "You step onto the dock. Mabel [[A]] is already there, haggling with the reeve over a coil of rope."
        with connect() as conn:
            world._place_new_people_at_arrival(conn, [], {"player": {"move_to_location": "The Dock"}}, self.LINE, prose)
            dock = int(conn.execute("SELECT id FROM locations WHERE code = 'L95'").fetchone()[0])
            now = int(conn.execute("SELECT location_id FROM npcs WHERE code = 'A'").fetchone()[0])
        self.assertEqual(now, dock)


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

    def test_a_building_named_through_its_door_is_entered(self):
        """8B run 150, T62: "I knock on the reeve's office door and go in" resolved no destination."""
        from app import world
        from app.db import connect

        _world("The Reeve's Office")
        line = "I knock on the reeve's office door and go in when I'm answered."
        prose = ("You knock on the reeve's office door and go in when you're answered. The reeve's door creaks open, revealing "
                 "a dimly lit room where the scent of ink lingers. A man in a threadbare cloak looks up as you enter.")
        with connect() as conn:
            harbour = int(conn.execute("SELECT id FROM locations WHERE code = 'L90'").fetchone()[0])
            before = int(conn.execute("SELECT COUNT(*) FROM locations").fetchone()[0])
            name = world._civic_building_requested(conn, harbour, line, prose)
            after = int(conn.execute("SELECT COUNT(*) FROM locations").fetchone()[0])
        self.assertEqual(name, "The Reeve's Office")
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
