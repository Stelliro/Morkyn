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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-run145-moves-"))
os.environ.setdefault("AI_RPG_DB", str(_TMP / "world.db"))
os.environ.setdefault("AI_RPG_CAMPAIGN_SLOTS", str(_TMP / "slots"))

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


if __name__ == "__main__":
    unittest.main()
