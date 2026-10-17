"""8B run 145, T6: a model MOVE the prose never shows does not stand on a travel line that names no place.

"I go aboard, check the dive lines for fraying and coil them ready" at the
Harbour Dock came back with MOVE "Salvage Guild's Tally House"; nothing in the
line or the prose went there, and the save put the player back in the tally
house. Only a line that sets off on a journey keeps the model's destination.

Run:  .venv\\Scripts\\python -m unittest tests.test_8b_run145_moves
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-run145-moves-"))
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


from app.world import _unasked_unshown_move  # noqa: E402

ROWS = [
    {"id": 1, "code": "L1", "name": "Saltmarrow", "parent_id": None, "kind": ""},
    {"id": 2, "code": "L2", "name": "Salvage Guild's Tally House", "parent_id": 1, "kind": ""},
    {"id": 3, "code": "L3", "name": "The Harbour", "parent_id": 1, "kind": ""},
    {"id": 4, "code": "L4", "name": "Harbour Dock", "parent_id": 1, "kind": ""},
]
T6_LINE = "\"Ropes and gear I can do.\" I go aboard, check the dive lines for fraying and coil them ready, then ask Orme which set of gear is mine."
T6_PROSE = (
    "“Ropes and gear I can do,” you say. The morning sun casts a pale glow over the Harbour Dock [[L4]]. You step "
    "aboard the boat, your boots clicking on the planks as you inspect the ropes and lines. You coil the ropes neatly. "
    "Orme [[C]] stands nearby. \"Your kit's over there,\" he says. \"You'll want to check it before we leave.\""
)


class AnUnshownMoveOnATravelLine(unittest.TestCase):
    def test_going_aboard_does_not_walk_back_to_the_tally_house(self):
        from app import world
        from app.db import connect, init_db

        init_db()
        world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
        with connect() as conn:
            town = int(conn.execute("SELECT current_location_id FROM player").fetchone()[0])
            tally = world._upsert_location(conn, "Salvage Guild's Tally House", "", parent_id=town, kind="")
            dock = world._upsert_location(conn, "Harbour Dock", "", parent_id=town, kind="")
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (int(dock),))
            result = {"narration": T6_PROSE, "player": {"move_to_location": "Salvage Guild's Tally House"}}
            report = world.resolve_movement(conn, result, T6_LINE, intent="travel", narration=T6_PROSE)
            self.assertEqual(report.get("status"), "dropped_unshown", report)
            self.assertFalse(result["player"].get("move_to_location"))
            conn.rollback()
        self.assertTrue(tally)

    def test_go_out_inside_speech_is_no_exit(self):
        # T7: '"... are we good to go out?"' read as a doorway exit and moved the player to the street.
        from app import world
        from app.db import connect, init_db

        init_db()
        world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
        line = ("I unwrap the oilcloth kit Orme pointed to and check it piece by piece: the weighted belt, the line, the knife. "
                "\"Anything missing, Captain, or are we good to go out?\"")
        prose = "The oilcloth kit lies open on the table. Orme [[C]] glances over. \"You're carrying the line,\" he says. \"That's all.\""
        with connect() as conn:
            town = int(conn.execute("SELECT current_location_id FROM player").fetchone()[0])
            tally = world._upsert_location(conn, "Salvage Guild's Tally House", "", parent_id=town, kind="")
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (int(tally),))
            result = {"narration": prose, "player": {}}
            report = world.resolve_movement(conn, result, line, intent="conversation", narration=prose)
            self.assertNotEqual((report or {}).get("rule"), "venue_exit", report)
            self.assertFalse(result["player"].get("move_to_location"), report)
            conn.rollback()

    def test_a_walk_inside_a_trade_line_still_resolves(self):
        # T45: "We row back to the dock ... carry the box up through town to the tally house and set it on the desk"
        # was a trade turn by its words and the walk was never resolved.
        from app import world
        from app.db import connect, init_db

        init_db()
        world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
        line = ("We row back to the dock with the box and the day's salvage. I carry the box up through town to the tally house "
                "and set it on the desk before Hugh to be counted and marked to my credit.")
        with connect() as conn:
            town = int(conn.execute("SELECT current_location_id FROM player").fetchone()[0])
            world._upsert_location(conn, "Salvage Guild's Tally House", "", parent_id=town, kind="")
            wreck = world._upsert_location(conn, "Wreck Site at Bay Mouth", "", parent_id=town, kind="")
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (int(wreck),))
            self.assertNotEqual(world._turn_intent(line)[0], "travel")
            self.assertEqual(world._movement_intent(conn, line), "travel")
            conn.rollback()

    def test_leaving_coin_on_a_counter_is_no_journey(self):
        # 8B run 146, T17: "I leave the six gold on his counter ... I turn for the door" kept a MOVE to the wreck.
        from app import world
        from app.db import connect, init_db

        init_db()
        world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
        line = ("I leave the six gold on his counter and pick up the hooded lamp and the flask of oil. "
                "\"Six is what they are worth, Theobald. Take it or leave it.\" I turn for the door.")
        prose = ("You leave the six gold on his counter and pick up the hooded lantern. Theobald Garner [[F]] watches you go. "
                 "You step out into the narrow street outside the Saltmarrow General Store [[L5]].")
        with connect() as conn:
            town = int(conn.execute("SELECT current_location_id FROM player").fetchone()[0])
            store = world._upsert_location(conn, "Saltmarrow General Store", "", parent_id=town, kind="general_store")
            world._upsert_location(conn, "Aegir's Wake", "", parent_id=town, kind="")
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (int(store),))
            result = {"narration": prose, "player": {"move_to_location": "Aegir's Wake"}}
            report = world.resolve_movement(conn, result, line, intent="travel", narration=prose)
            self.assertNotEqual(result["player"].get("move_to_location"), "Aegir's Wake", report)
            conn.rollback()

    def test_a_journey_keeps_the_models_destination(self):
        line = "I leave the dock and head out along the shore road before the tide turns."
        prose = "You leave the dock behind, the shore road rising ahead of you between the salt grass."
        patch = {"move_to_location": "Shore Road", "move_to_location_code": None}
        self.assertEqual(_unasked_unshown_move({}, patch, ROWS, line, intent="travel", narration=prose, current_name="Harbour Dock"), "")

    def test_a_place_the_line_names_stands(self):
        line = "I go back up to the tally house to ask about the pay."
        prose = "You climb the path and push the tally house door open; the tallyman looks up."
        patch = {"move_to_location": "Salvage Guild's Tally House", "move_to_location_code": None}
        self.assertEqual(_unasked_unshown_move({}, patch, ROWS, line, intent="travel", narration=prose, current_name="Harbour Dock"), "")

    def test_a_place_the_prose_reaches_stands(self):
        line = "I go down to the water."
        prose = "You walk down past the crates until the harbour opens before you, boats knocking at their moorings."
        patch = {"move_to_location": "The Harbour", "move_to_location_code": None}
        self.assertEqual(_unasked_unshown_move({}, patch, ROWS, line, intent="travel", narration=prose, current_name="Salvage Guild's Tally House"), "")


FLAT_ROWS = [
    {"id": 1, "code": "L1", "name": "Saltmarrow", "parent_id": None, "kind": ""},
    {"id": 3, "code": "L3", "name": "The Old Wharf", "parent_id": 1, "kind": ""},
    {"id": 7, "code": "L7", "name": "The Flats", "parent_id": None, "kind": ""},
    {"id": 8, "code": "L8", "name": "Edge of the Flats", "parent_id": None, "kind": ""},
]


class ASpokenRequestIsNotAWalk(unittest.TestCase):
    """8B run 147, T26 and T32: "Row me out to the wreck now" moved the player while the prose stayed on the dock."""

    def _rows(self):
        from app import world
        from app.db import connect, init_db

        init_db()
        world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
        return world, connect

    def test_a_request_the_prose_answers_with_talk_moves_nobody(self):
        world, connect = self._rows()
        line = "I thank Eda and go back to Wulfstan at the end of the dock. \"The water's near its lowest by my reckoner. Row me out to the wreck now.\""
        prose = ("You make your way toward Wulfstan Orme [[C]]'s stall at the end of the dock. Wulfstan's brow furrows. "
                 "\"Aye, the tides are right. But you'll need a rowing pole, and the current's strong.\"")
        with connect() as conn:
            town = int(conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()[0])
            harbour = world._upsert_location(conn, "The Harbour", "", parent_id=town, kind="")
            wreck = world._upsert_location(conn, "The Wrecked Skiff", "A half-sunken ship in the mudflats.")
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (int(harbour),))
            result = {"narration": prose, "player": {"move_to_location": "The Wrecked Skiff"}}
            world.resolve_movement(conn, result, line, intent="travel", narration=prose)
            self.assertNotEqual(result["player"].get("move_to_location"), "The Wrecked Skiff")
            self.assertNotEqual(str(result["player"].get("move_to_location_code") or ""), f"L{int(wreck)}")
            conn.rollback()

    def test_a_walk_the_prose_keeps_in_the_current_place_goes_nowhere_else(self):
        # 8B run 147, T75: "walk east along the flats" with MOVE "The Drowned Claim" moved the player off the flats.
        world, connect = self._rows()
        line = "I walk east along the flats toward the line of sand and brine she pointed at, watching the mud for the prow of a half-sunk wreck."
        with connect() as conn:
            flats = world._upsert_location(conn, "The Flats", "Mud and salt to the horizon.")
            world._upsert_location(conn, "The Drowned Claim", "Ruins the sea left.")
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (int(flats),))
            prose = (f"You walk east along The Flats [[L{int(flats)}]], the sand and brine she pointed at now a line of soft, wet earth. "
                     "You watch the muddy ground closely, hoping to spot the prow of a wrecked ship.")
            result = {"narration": prose, "player": {"move_to_location": "The Drowned Claim"}}
            report = world.resolve_movement(conn, result, line, intent="travel", narration=prose)
            self.assertIsNone(result["player"].get("move_to_location"), report)
            conn.rollback()

    def test_a_question_about_the_walk_with_the_path_only_pointed_at_moves_nobody(self):
        # 8B run 147, T98: asking whether the storm had passed enough to walk to the Claim moved the player there.
        world, connect = self._rows()
        line = "\"He owes, not me, Abel.\" I finish the ale and ask whether the storm has passed enough to walk to the Drowned Claim."
        with connect() as conn:
            town = int(conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()[0])
            inn = world._upsert_location(conn, "The Stag and Heron", "", parent_id=town, kind="inn")
            claim = world._upsert_location(conn, "The Drowned Claim", "Ruins the sea left.")
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (int(inn),))
            prose = ("You finish the ale and fix Abel with a glare. \"The sea's still in a mood,\" he says. The thought lingers as "
                     f"you step into the rain, the cold biting through your wool tunic. The path to The Drowned Claim [[L{int(claim)}]] is uncertain.")
            result = {"narration": prose, "player": {"move_to_location": "The Drowned Claim"}}
            report = world.resolve_movement(conn, result, line, intent="travel", narration=prose)
            self.assertIsNone(result["player"].get("move_to_location"), report)
            conn.rollback()

    def test_a_request_the_prose_carries_out_still_moves(self):
        world, connect = self._rows()
        line = "I climb into the skiff. \"Out to the wreck, Wulfstan.\""
        prose = "You climb into the skiff and Wulfstan pushes off. The current pulls you out across the flats to the wreck's broken hull."
        with connect() as conn:
            town = int(conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()[0])
            harbour = world._upsert_location(conn, "The Harbour", "", parent_id=town, kind="")
            world._upsert_location(conn, "The Wrecked Skiff", "A half-sunken ship in the mudflats.")
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (int(harbour),))
            result = {"narration": prose, "player": {"move_to_location": "The Wrecked Skiff"}}
            report = world.resolve_movement(conn, result, line, intent="travel", narration=prose)
            self.assertIn("Wrecked Skiff", str(report.get("destination") or result["player"].get("move_to_location") or ""), report)
            conn.rollback()


class AKnownPlaceUnderItsCommonNoun(unittest.TestCase):
    """8B run 147, T40: "When we reach the wreck I set the anchor" named no destination; the save stayed at the harbour."""

    ROWS = [
        {"id": 1, "code": "L1", "name": "Saltmarrow", "parent_id": None, "kind": ""},
        {"id": 3, "code": "L3", "name": "The Harbour", "parent_id": 1, "kind": ""},
        {"id": 6, "code": "L6", "name": "The Wrecked Skiff", "parent_id": None, "kind": ""},
        {"id": 7, "code": "L7", "name": "Tally House", "parent_id": 1, "kind": ""},
        {"id": 8, "code": "L8", "name": "Reeve's House", "parent_id": 1, "kind": ""},
    ]

    def test_the_wreck_is_the_wrecked_skiff(self):
        from app.world import _movement_destination_from_input

        row = _movement_destination_from_input(self.ROWS, "When we reach the wreck I set the anchor into the mud beside the hull.", "The Harbour")
        self.assertEqual(row["name"], "The Wrecked Skiff")

    def test_an_ambiguous_noun_names_nothing(self):
        from app.world import _movement_destination_from_input

        self.assertIsNone(_movement_destination_from_input(self.ROWS, "I walk over to the house and knock.", "Saltmarrow"))

    def test_a_noun_left_behind_names_nothing(self):
        from app.world import _movement_destination_from_input

        self.assertIsNone(_movement_destination_from_input(self.ROWS, "I leave the wreck and sit in the skiff.", "The Wrecked Skiff"))


class APossessivePartIsThePlace(unittest.TestCase):
    """8B run 147, T45: "the Drowned Claim's ruins" was made beside "The Drowned Claim"."""

    def test_the_claims_ruins_are_the_claim(self):
        from app.world import _same_place_name

        self.assertTrue(_same_place_name("the Drowned Claim's ruins", "The Drowned Claim"))
        self.assertTrue(_same_place_name("The Harbour", "the Harbour’s edge"))

    def test_another_places_part_is_not_this_one(self):
        from app.world import _same_place_name

        self.assertFalse(_same_place_name("the Drowned Claim's ruins", "The Harbour"))
        self.assertFalse(_same_place_name("the Drowned District Chapel", "The Drowned District"))


class ThePlaceLeftIsNotTheDestination(unittest.TestCase):
    """8B run 146, T49: "I leave the flats ... and set off north" moved the player into The Flats."""

    def test_leaving_the_flats_names_no_destination(self):
        from app.world import _movement_destination_from_input

        line = ("I leave the flats before the tide covers them and set off north out of town along the road, "
                "to find the well-keeper Rolf Joliffe.")
        self.assertIsNone(_movement_destination_from_input(FLAT_ROWS, line, "Edge of the Flats"))

    def test_shelter_from_the_storm_in_a_place_goes_there(self):
        # 8B run 147, T96: "take shelter from the storm in the Stag and Heron" read the inn as the origin.
        from app.world import _movement_destination_from_input

        rows = FLAT_ROWS + [{"id": 9, "code": "L9", "name": "The Stag and Heron", "parent_id": 1, "kind": "inn"}]
        row = _movement_destination_from_input(rows, "I take shelter from the storm in the Stag and Heron and wait it out by the fire.", "The Flats")
        self.assertEqual(row["name"], "The Stag and Heron")

    def test_a_place_as_a_possessive_is_no_destination(self):
        # 8B run 148, T16: "the Mistral's hold is emptied" moved the player back aboard the Mistral.
        from app.world import _movement_destination_from_input

        rows = FLAT_ROWS + [{"id": 5, "code": "L5", "name": "The Mistral", "parent_id": 3, "kind": ""}]
        line = "I tell the Reeve plainly that the Mistral's hold is emptied onto the cart and ask for the thirty gold for the haul."
        self.assertIsNone(_movement_destination_from_input(rows, line, "The Harbour"))
        row = _movement_destination_from_input(rows, "I walk back to the Mistral to check the hold.", "The Harbour")
        self.assertEqual(row["name"], "The Mistral")
        # 8B run 148, T18: "the thirty gold for the Mistral haul" moved the player aboard the Mistral.
        line = "In the morning I find Roderic at the harbour and walk with him to the Reeve's office to collect the thirty gold for the Mistral haul."
        self.assertIsNone(_movement_destination_from_input(rows, line, "The Stag and Heron"))

    def test_the_place_walked_to_after_leaving_one_is_the_destination(self):
        from app.world import _movement_destination_from_input

        row = _movement_destination_from_input(FLAT_ROWS, "I leave the flats and walk back to the Old Wharf.", "Edge of the Flats")
        self.assertEqual(row["name"], "The Old Wharf")

    def test_a_meeting_arranged_for_later_is_no_walk_now(self):
        # 8B run 146, T85: '"We go at the next low tide. Meet me at the Old Wharf at first light."' moved the player there.
        from app.world import _movement_destination_from_input

        line = "\"Then come with me yourself, Elara. We go at the next low tide. Meet me at the Old Wharf at first light.\""
        self.assertIsNone(_movement_destination_from_input(FLAT_ROWS, line, "Edge of the Flats"))
        # Asking to go now still walks.
        row = _movement_destination_from_input(FLAT_ROWS, "\"We go to the Old Wharf now, Elara.\"", "Edge of the Flats")
        self.assertEqual(row["name"], "The Old Wharf")

    def test_a_question_told_names_no_destination(self):
        # 8B run 146, T89: "ask what a tide chart of the Mire's Breath would cost" walked the player out of the store.
        from app.world import _movement_destination_from_input

        rows = FLAT_ROWS + [{"id": 9, "code": "L9", "name": "The Mire's Breath", "parent_id": None, "kind": ""}]
        line = "I pay the storekeeper for the rope and the oil, and ask what a tide chart of the Mire's Breath would cost."
        self.assertIsNone(_movement_destination_from_input(rows, line, "Saltmarrow General Store"))
        row = _movement_destination_from_input(rows, "I ask Theobald the price, then set out for the Mire's Breath.", "Saltmarrow General Store")
        self.assertEqual(row["name"], "The Mire's Breath")

    def test_from_one_place_to_another_goes_to_the_second(self):
        from app.world import _movement_destination_from_input

        row = _movement_destination_from_input(FLAT_ROWS, "I walk from the Old Wharf out to the flats.", "Saltmarrow")
        self.assertEqual(row["name"], "The Flats")


if __name__ == "__main__":
    unittest.main()
