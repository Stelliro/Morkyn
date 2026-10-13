"""Name fixes from the ninth Saltmarrow run on Qwen2.5 7B: what a find is called, and "The X at <Town>" inns."""
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-7b-run9-names-"))
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


def seed() -> None:
    """Run 9's world before the opening: Saltmarrow and nothing else."""
    from app import db
    from app.db import connect

    db.init_db()
    with connect() as conn:
        conn.execute("UPDATE player SET current_location_id = 1 WHERE id = 1")
        conn.execute("DELETE FROM npcs")
        conn.execute("DELETE FROM inventory")
        conn.execute("DELETE FROM locations WHERE id != 1")
        conn.execute(
            "UPDATE locations SET code = 'L1', name = 'Saltmarrow', "
            "summary = 'Starting location for a frontier dark fantasy playthrough.', parent_id = 0, "
            "kind = '', settlement_size = 'town', keeper_npc_id = 0 WHERE id = 1"
        )


T3_PROSE = (
    "You pick up the glinting thing you found and wipe the dirt off it on your sleeve to inspect it. The piece is "
    "a small, worn coin with a rough edge and a faded symbol that looks like a seagull. If it's worth anything, "
    "you slip it into your pocket."
)
T3_LINE = (
    "I pick up the glinting thing I found and wipe the mud off it on my sleeve to see what it is. "
    "If it's worth anything, it goes in my pocket."
)
T0_PROSE = (
    "To your left, the ruins of a former warehouse stand abandoned. The Badger at Saltmarrow, a small inn, "
    "stands just beyond the warehouse. Its sign creaks in the wind, and smoke rises from its chimney. "
    "The Pike at Saltmarrow, a pub, is visible as well, its windows dark and unlit."
)


class AFindIsCalledWhatTheProseCallsIt(unittest.TestCase):
    """T3: the pack held 'glinting thing you found' for 'a small, worn coin ... like a seagull'."""

    def test_prose_name_for_a_vague_take(self):
        from app.world import _prose_named_thing

        self.assertEqual(_prose_named_thing("glinting thing you found", T3_PROSE), "worn seagull coin")
        self.assertEqual(_prose_named_thing("rusty key", T3_PROSE), "rusty key")
        self.assertEqual(_prose_named_thing("thing you found", "You pick up the thing you found."), "thing")

    def test_ground_acquisitions_grants_the_prose_name(self):
        from app.world import ground_acquisitions

        turn: dict = {}
        granted = ground_acquisitions(turn, T3_PROSE, {"inventory": []}, player_input=T3_LINE)
        self.assertEqual(granted, ["worn seagull coin"])

    def test_a_curio_coin_is_not_gold(self):
        from app.world import _coin_name_match

        self.assertFalse(_coin_name_match("worn seagull coin"))


class TheXAtTownIsAnInn(unittest.TestCase):
    """T0: 'The Badger at Saltmarrow, a small inn' and 'The Pike at Saltmarrow, a pub' were not recorded."""

    def test_named_with_at_the_town(self):
        from app import world

        found = world._named_buildings_in("The Badger at Saltmarrow, a small inn, stands just beyond the warehouse.")
        self.assertIn(("Badger at Saltmarrow", "small inn"), found)

    def test_recorded_in_the_town(self):
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            made = world._record_named_buildings(conn, T0_PROSE)
            self.assertIn("The Badger at Saltmarrow", made)
            badger = conn.execute("SELECT * FROM locations WHERE name = 'The Badger at Saltmarrow'").fetchone()
            self.assertEqual((badger["parent_id"], badger["kind"]), (1, "inn"))

    def test_far_off_is_still_far(self):
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            made = world._record_named_buildings(
                conn, "The Gull at Redmoor, an inn, stands beyond the flats on the distant horizon."
            )
            self.assertEqual(made, [])

    def test_the_towns_generic_tavern_is_still_not_a_name(self):
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            made = world._record_named_buildings(conn, "You glance at the Saltmarrow tavern across the square.")
            self.assertEqual(made, [])


class CodedNamesKeepTheirCase(unittest.TestCase):
    """T3: 'the old tideside [[L3]]' for the place stored as 'Old Tideside'."""

    def test_stored_case(self):
        from app.llm import _coded_names_in_stored_case

        self.assertEqual(
            _coded_names_in_stored_case("The wind whips through the old tideside [[L3]].", {"L3": "Old Tideside"}),
            "The wind whips through the Old Tideside [[L3]].",
        )
        # Only the words right before that code.
        self.assertEqual(
            _coded_names_in_stored_case("the old tideside is quiet near Saltmarrow [[L1]].", {"L3": "Old Tideside"}),
            "the old tideside is quiet near Saltmarrow [[L1]].",
        )


class AThingIntoAPocketIsNotTravel(unittest.TestCase):
    """T3: 'it goes in my pocket' journaled a travel turn with no destination."""

    def test_pocket_is_not_travel(self):
        from app.world import travel_intent

        self.assertFalse(travel_intent(T3_LINE))
        self.assertTrue(travel_intent("I go into the inn."))
        self.assertTrue(travel_intent("The coin goes into my purse and I walk to the harbour."))


if __name__ == "__main__":
    unittest.main()
