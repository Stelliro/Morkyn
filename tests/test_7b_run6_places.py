"""Place fixes from the sixth Saltmarrow run on Qwen2.5 7B (round 2 of the run-5 place work)."""
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-7b-run6-places-"))
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
    """Run 6's world at T3: Saltmarrow and nothing else."""
    from app import db
    from app.db import connect

    db.init_db()
    with connect() as conn:
        conn.execute("UPDATE player SET current_location_id = 1 WHERE id = 1")
        conn.execute("DELETE FROM npcs")
        conn.execute("DELETE FROM locations WHERE id != 1")
        conn.execute(
            "UPDATE locations SET code = 'L1', name = 'Saltmarrow', "
            "summary = 'Starting location for a frontier dark fantasy playthrough.', parent_id = 0, "
            "kind = '', settlement_size = 'town', keeper_npc_id = 0 WHERE id = 1"
        )


def row(conn, name):
    return conn.execute("SELECT * FROM locations WHERE name = ?", (name,)).fetchone()


T3_LINE = (
    "\"Then I'd best get my hauling done before they pick the lower district clean.\" I nod to Simon and head "
    "down to the salvage yard to see what the overseer has on the board today."
)
T3_PROSE = (
    "You nod to Simon Pennick [[A]] and head down to the salvage yard, the sun casting long shadows in the early "
    "light of the day. The lower district is already bustling with salvagers setting up their tents and carts. "
    "The overseer, a grizzled man named Oldfield, is scribbling something on a ledger. You approach him, ready to "
    "see what tasks he has for you."
)
T9_LINE = (
    "I follow Oldfield to the shed door before he can get away. \"Oldfield. Two gold, by noon, we said. It's not "
    "noon and the pile's done.\""
)
T9_PROSE = (
    "You follow Oldfield [[B]] to the shed door before he can get away. \"Oldfield. Two gold, by noon, we said. "
    "It's not noon and the pile's done.\" Oldfield [[B]] stops and turns, a hint of surprise on his face.\n\n"
    "The sorting shed [[L2]] is a cluttered space, filled with crates and bales of various salvaged items.\n\n"
    "Oldfield [[B]] gives you a nod of approval. \"Well, you've earned this.\""
)
T0_PROSE = (
    "You stand on the edge of Saltmarrow, where the high tide marks the boundary between the living and the "
    "drowned.\n\nOn your right, the Elwood and Daughters dairy stands open, its wooden door creaking gently in the "
    "morning breeze. To the west, the Anchor and Ox inn is closed for the morning, its shutters tightly closed. In "
    "the distance, the Badger at Saltmarrow, a familiar sight, is also quiet, its windows dark."
)


class AShedStandsInTheTown(unittest.TestCase):
    """T4: 'Sorting shed' was minted top-level, a second town beside Saltmarrow."""

    def test_outbuilding_is_the_towns_child(self):
        from app.db import connect
        from app.world import _upsert_location

        seed()
        with connect() as conn:
            _upsert_location(conn, "Sorting shed", "A small shed filled with salvaged goods, ready to be sorted")
            self.assertEqual(int(row(conn, "Sorting shed")["parent_id"]), 1)
            self.assertEqual(str(row(conn, "Sorting shed")["kind"] or ""), "")

    def test_inside_a_child_the_new_one_is_the_towns_too(self):
        from app.db import connect
        from app.world import _upsert_location

        seed()
        with connect() as conn:
            shed = _upsert_location(conn, "Sorting shed", "")
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (shed,))
            _upsert_location(conn, "Net loft", "")
            self.assertEqual(int(row(conn, "Net loft")["parent_id"]), 1)

    def test_roads_far_places_and_plain_names_stay_top_level(self):
        from app.db import connect
        from app.world import _upsert_location

        seed()
        with connect() as conn:
            _upsert_location(conn, "Coast Road", "The road north along the dunes.")
            _upsert_location(conn, "Redhill", "A village two days' walk inland.")
            _upsert_location(conn, "Boathouse", "An old boathouse across the bay, beyond the point.")
            for name in ("Coast Road", "Redhill", "Boathouse"):
                with self.subTest(name=name):
                    self.assertEqual(int(row(conn, name)["parent_id"]), 0)


class AMoveToWhereYouStandIsNoTrip(unittest.TestCase):
    """8B run 10, T0: "MOVE to Saltmarrow dropped" while the player stood in Saltmarrow."""

    def test_no_drop_note(self):
        from app import world
        from app.db import connect

        seed()
        prose = "You stand on the edge of the flats. A narrow path leads toward the town of Saltmarrow [[L1]]."
        with connect() as conn:
            result = {"player": {"move_to_location": "Saltmarrow"}, "narration": prose}
            report = world.resolve_movement(conn, result, "", intent="opening", narration=prose)
            here = conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()[0]
        self.assertNotEqual(report.get("status"), "dropped_unshown")
        self.assertEqual(int(here), 1)


class FollowingToTheDoorIsNoJourney(unittest.TestCase):
    """T9: 'I follow Oldfield to the shed door' counted as travel, so a MOVE out to Saltmarrow stood."""

    def test_travel_intent(self):
        from app.world import travel_intent

        self.assertFalse(travel_intent(T9_LINE))
        self.assertFalse(travel_intent("I walk over to the counter and set the fittings down."))
        self.assertTrue(travel_intent(T3_LINE))
        self.assertTrue(travel_intent("I follow her out of the inn and down to the harbour."))
        self.assertTrue(travel_intent("I follow Oldfield."))

    def test_the_move_out_is_dropped(self):
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            shed = world._upsert_location(conn, "Sorting shed", "")
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (shed,))
            result = {"player": {"move_to_location": "Saltmarrow"}, "narration": T9_PROSE}
            report = world.resolve_movement(conn, result, T9_LINE, intent="claim_check", narration=T9_PROSE)
        self.assertEqual(report["status"], "dropped_unshown")
        self.assertIsNone(result["player"]["move_to_location"])


class WalkingToANamedBuilding(unittest.TestCase):
    """T3: 'I head down to the salvage yard' in a world of one place left her in the square."""

    def test_the_yard_is_made_and_reached(self):
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            result = {"player": {}, "narration": T3_PROSE}
            report = world.resolve_movement(conn, result, T3_LINE, intent="travel", narration=T3_PROSE)
            self.assertEqual((report["status"], report.get("rule")), ("repaired", "venue_requested"))
            yard = row(conn, report["destination"])
            self.assertIsNotNone(yard)
            self.assertEqual((int(yard["parent_id"]), str(yard["kind"])), (1, "salvage_yard"))
            self.assertEqual(result["player"]["move_to_location"], str(yard["name"]))
            # The second time it is found, not made again.
            again = world._venue_requested_and_reached(conn, T3_LINE, T3_PROSE, "L1")
            self.assertEqual(again, str(yard["name"]))
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM locations WHERE kind = 'salvage_yard'").fetchone()[0], 1)

    def test_not_when_the_prose_stays(self):
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            prose = "Simon shakes his head. \"The salvage yard is shut till the bell,\" he says. You stay by the wall."
            self.assertEqual(world._venue_requested_and_reached(conn, T3_LINE, prose, "L1"), "")
            self.assertEqual(
                world._venue_requested_and_reached(conn, "What does the salvage yard pay?", T3_PROSE, "L1"), ""
            )


class BuildingsNamedInPassing(unittest.TestCase):
    """T0: the opening named an inn and a dairy in Saltmarrow and neither was made."""

    def test_recorded_as_the_towns_children(self):
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            made = world._record_named_buildings(conn, T0_PROSE)
            self.assertEqual(sorted(made), ["Elwood and Daughters Dairy", "The Anchor and Ox"])
            inn = row(conn, "The Anchor and Ox")
            self.assertEqual((int(inn["parent_id"]), str(inn["kind"])), (1, "inn"))
            self.assertEqual(int(row(conn, "Elwood and Daughters Dairy")["parent_id"]), 1)
            # Once known, not made twice.
            self.assertEqual(world._record_named_buildings(conn, T0_PROSE), [])

    def test_speech_and_far_off_are_not_recorded(self):
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            prose = (
                "\"The Crooked Mast tavern serves the worst ale on the coast,\" Simon says. "
                "Far out across the flats, the Gull Rock lighthouse blinks."
            )
            self.assertEqual(world._record_named_buildings(conn, prose), [])


class NoTownCodeOnAnInn(unittest.TestCase):
    """T0: 'the Badger at Saltmarrow [[L1]]' - the town's code read as the inn's."""

    def test_tail_of_a_longer_name_is_not_tagged(self):
        from app.llm import _inject_entity_codes_for_known_names

        out = _inject_entity_codes_for_known_names(T0_PROSE, {"L1": "Saltmarrow"})
        self.assertIn("the Badger at Saltmarrow, a familiar sight", out)
        self.assertIn("edge of Saltmarrow [[L1]]", out)
        out = _inject_entity_codes_for_known_names("Back in Saltmarrow, the tide turns.", {"L1": "Saltmarrow"})
        self.assertIn("Back in Saltmarrow [[L1]]", out)


if __name__ == "__main__":
    unittest.main()
