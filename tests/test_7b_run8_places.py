"""Place fixes from the eighth Saltmarrow run on Qwen2.5 7B: the player's own walks, and the opening's buildings."""
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-7b-run8-places-"))
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
    """Run 8's world before the opening: Saltmarrow and nothing else."""
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


T0_PROSE = (
    "You stand on the salt-scented flats of Saltmarrow [[L1]], the harbour town that the sea abandoned forty "
    "years ago.\n\nTo your left, the Wandering Ox Chandlery stands open, its door ajar and the scent of oil and "
    "salted leather wafting out. To your right, the Wren's Rest, a modest inn, beckons with the promise of warmth "
    "and rest. Linnet [[B]] Eastlake, the hayward, is sweeping the path in front of the Wren's Rest.\n\n"
    "\"Good morning,\" Linnet [[B]] calls out.\n\nYou glance at your mother's brass tide-reckoner. You step "
    "towards the Wren's Rest, the door creaking softly as you enter, and Linnet [[B]] follows you in.\n\n"
    "The Wren's Rest is cozy, with rough-hewn tables and benches."
)
T2_LINE = (
    "\"Then I'd better catch that lull.\" I finish the ale, leave a copper on the table, and head out of the inn "
    "toward the salvage yard to see what's posted."
)
T2_PROSE = (
    "“Then I'd better catch that lull,” you say. You finish the last of your morning drink, leaving a "
    "copper on the table. You step out into the street, the salty air of Saltmarrow [[L1]] greeting you. The "
    "salvage yard is still a bit distant, but you can see the outlines of the crates and the wooden posts marking "
    "the area where salvagers gather. You head in that direction. The walk to the salvage yard is brisk, and as "
    "you near, you see a few salvagers already there, their gear ready for the day. A sign by the entrance lists "
    "the current tasks and postings. You approach and begin to read through the notices."
)
T4_LINE = (
    "Fifty copper is better than nothing. I walk back to the Wren's Rest and ask whoever is behind the bar "
    "where I can find Madoc."
)
T4_PROSE = (
    "You walk back to the Wren's Rest, the fog thickening as the day wears on. You ask the person behind the "
    "bar where you can find Madoc."
)


class OpeningBuildings(unittest.TestCase):
    def setUp(self):
        seed()

    def test_buildings_named_in_the_opening_are_recorded_in_the_town(self):
        from app import world
        from app.db import connect

        with connect() as conn:
            made = world._record_named_buildings(conn, T0_PROSE)
            inn = row(conn, "The Wren's Rest")
            shop = row(conn, "Wandering Ox Chandlery")
        self.assertIn("The Wren's Rest", made)
        self.assertIsNotNone(inn)
        self.assertEqual((inn["parent_id"], inn["kind"]), (1, "inn"))
        self.assertIsNotNone(shop)
        self.assertEqual(shop["parent_id"], 1)
        self.assertTrue(shop["kind"])

    def test_the_opening_starts_inside_the_building_it_enters(self):
        from app import world
        from app.db import connect

        with connect() as conn:
            world._record_named_buildings(conn, T0_PROSE)
            self.assertEqual(world._opening_entry(conn, T0_PROSE), "The Wren's Rest")

    def test_titles_trades_and_the_town_are_not_new_buildings(self):
        """Shapes a replay of runs 5-8 caught: a person's title, a bare trade, the town's own tavern."""
        from app import world
        from app.db import connect

        prose = (
            "You find the Overseer of Saltmarrow Salvage Yard at his desk. You cross the Salvage Yard to the gate. "
            "The Saltmarrow tavern is quiet at this hour."
        )
        with connect() as conn:
            before = conn.execute("SELECT COUNT(*) FROM locations").fetchone()[0]
            made = world._record_named_buildings(conn, prose)
            after = conn.execute("SELECT COUNT(*) FROM locations").fetchone()[0]
        self.assertEqual(made, [])
        self.assertEqual(before, after)

    def test_passing_a_building_is_not_entering_it(self):
        from app import world
        from app.db import connect

        prose = "To your right, the Wren's Rest, a modest inn, beckons. You walk past the Wren's Rest toward the flats."
        with connect() as conn:
            world._record_named_buildings(conn, prose)
            self.assertEqual(world._opening_entry(conn, prose), "")


class TheWalkThePlayerAsksFor(unittest.TestCase):
    def setUp(self):
        seed()

    def test_t2_a_walk_toward_the_yard_gets_there(self):
        from app import world
        from app.db import connect

        with connect() as conn:
            got = world._venue_requested_and_reached(conn, T2_LINE, T2_PROSE, "L1")
            yard = row(conn, got) if got else None
        self.assertTrue(got)
        self.assertIsNotNone(yard)
        self.assertEqual((yard["parent_id"], yard["kind"]), (1, "salvage_yard"))

    def test_t4_a_walk_to_a_building_by_name_gets_there(self):
        from app import world
        from app.db import connect

        with connect() as conn:
            got = world._venue_requested_and_reached(conn, T4_LINE, T4_PROSE, "L1")
            made = row(conn, "The Wren's Rest")
        self.assertEqual(got, "The Wren's Rest")
        self.assertIsNotNone(made)
        self.assertEqual(made["parent_id"], 1)

    def test_t4_a_known_building_is_that_building(self):
        from app import world
        from app.db import connect

        with connect() as conn:
            world._record_named_buildings(conn, T0_PROSE)
            before = conn.execute("SELECT COUNT(*) FROM locations").fetchone()[0]
            got = world._venue_requested_and_reached(conn, T4_LINE, T4_PROSE, "L1")
            after = conn.execute("SELECT COUNT(*) FROM locations").fetchone()[0]
        self.assertEqual(got, "The Wren's Rest")
        self.assertEqual(before, after)

    def test_the_prose_can_still_stop_the_walk(self):
        from app import world
        from app.db import connect

        prose = "You head toward the salvage yard, but the salvage yard gate is locked and no one answers."
        with connect() as conn:
            self.assertEqual(world._venue_requested_and_reached(conn, T2_LINE, prose, "L1"), "")

    def test_a_question_or_speech_is_not_a_walk(self):
        from app import world
        from app.db import connect

        with connect() as conn:
            line = "\"Shouldn't you be at the Wren's Rest, Linnet?\" I ask."
            prose = "Linnet shrugs. \"The Wren's Rest can wait,\" she says. You stay by the trough."
            self.assertEqual(world._venue_requested_and_reached(conn, line, prose, "L1"), "")

    def test_looking_for_a_person_is_not_a_building(self):
        from app import world
        from app.db import connect

        with connect() as conn:
            line = "I go looking for Madoc and ask around the square."
            prose = "You walk across the square asking after Madoc. Nobody has seen Madoc today."
            self.assertEqual(world._venue_requested_and_reached(conn, line, prose, "L1"), "")
            self.assertIsNone(row(conn, "The Madoc"))


class ThroughTheTurn(unittest.TestCase):
    """The same turns through resolve_movement and apply_turn, not only the helpers."""

    def setUp(self):
        seed()

    def _here(self):
        from app.db import connect

        with connect() as conn:
            loc = conn.execute(
                "SELECT l.name FROM player p JOIN locations l ON l.id = p.current_location_id WHERE p.id = 1"
            ).fetchone()
        return loc[0] if loc else ""

    def test_t2_resolve_movement_walks_to_the_yard(self):
        from app import world
        from app.db import connect

        result = {"narration": T2_PROSE, "player": {}}
        with connect() as conn:
            report = world.resolve_movement(conn, result, T2_LINE, intent="travel", narration=T2_PROSE)
        self.assertEqual(report.get("rule"), "venue_requested", report)

    def test_t4_resolve_movement_walks_to_the_inn(self):
        from app import world
        from app.db import connect

        result = {"narration": T4_PROSE, "player": {}}
        with connect() as conn:
            report = world.resolve_movement(conn, result, T4_LINE, intent="travel", narration=T4_PROSE)
        self.assertEqual(report.get("destination"), "The Wren's Rest", report)

    def test_opening_apply_starts_inside_the_inn(self):
        from app import world

        result = {"narration": T0_PROSE, "player": {}}
        world.apply_turn(result, "", input_kind="opening", prompt_context={})
        self.assertEqual(self._here(), "The Wren's Rest")


if __name__ == "__main__":
    unittest.main()
