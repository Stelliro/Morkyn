"""Regression tests for venues: containment, hours, commonality, keeper identity.

Every case here comes from a live probe that walked into an apothecary on a
square and found the game had recorded nothing at all: no location, no movement,
no way back. Asking to return from two places away minted a second, unrelated
"Apothecary" and teleported the player inside it, at night, to be served by a
keeper who was a man on the first visit, a woman on the second, and a different
man on the third.

Run:  python -m unittest tests.test_venues
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-venues-test-"))
_ENV = {
    "AI_RPG_DB": str(_TMP / "world.db"),
    "AI_RPG_PACK_DIR": str(_TMP / "packs"),
    "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
    "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
    "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
    "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
}
os.environ.update(_ENV)

import app.venues as venues  # noqa: E402
import app.world as world  # noqa: E402
from app.db import connect, db_path, init_db  # noqa: E402


def _assert_isolated() -> None:
    if not str(db_path()).startswith(str(_TMP)):
        raise AssertionError(f"test isolation failed: AI_RPG_DB resolves to {db_path()!r}")


def setUpModule() -> None:
    """Re-pin paths: unittest imports every test module before running any test."""
    os.environ.update(_ENV)
    _assert_isolated()


_assert_isolated()
init_db()

HOUR = 60


class TestKindClassification(unittest.TestCase):
    def test_names_that_state_their_kind(self):
        for name, kind in (
            ("Brimmer Apothecary", "apothecary"),
            ("Gedra Forge", "smithy"),
            ("Old Bakehouse", "bakery"),
            ("The Kettle and Crow Inn", "inn"),
            ("Market Hall", "market_hall"),
            ("Silverhand Goldsmith", "jeweller"),
        ):
            with self.subTest(name=name):
                self.assertEqual(venues.venue_kind_from_name(name), kind)

    def test_open_places_are_not_venues(self):
        for name in ("Brimmer Square", "East Road", "Thistle Woods", "Riverbend Camp"):
            with self.subTest(name=name):
                self.assertEqual(venues.venue_kind_from_name(name), "")

    def test_trade_words_in_possessive_names_are_not_shops(self):
        """"The Alchemist's Rest" is an inn borrowing a trade word, not an alchemist."""
        for name in ("The Alchemist's Rest", "The Smith's Arms", "Baker's Row"):
            with self.subTest(name=name):
                self.assertEqual(venues.venue_kind_from_name(name), "")

    def test_longest_phrase_wins(self):
        self.assertEqual(venues.venue_kind_from_name("The Guild Hall"), "guild_hall")
        self.assertEqual(venues.venue_kind_from_name("Grand Market Hall"), "market_hall")


class TestOpeningHours(unittest.TestCase):
    def test_ordinary_window(self):
        for minute, expected in ((7 * HOUR, False), (9 * HOUR, True), (17 * HOUR, True), (19 * HOUR, False)):
            with self.subTest(minute=minute):
                self.assertEqual(venues.is_open(8 * HOUR, 18 * HOUR, minute), expected)

    def test_window_wrapping_past_midnight(self):
        """A tavern open 11:00-02:00 has close < open; 01:00 is inside it, 03:00 is not."""
        for minute, expected in ((10 * HOUR, False), (12 * HOUR, True), (23 * HOUR, True),
                                 (1 * HOUR, True), (3 * HOUR, False)):
            with self.subTest(minute=minute):
                self.assertEqual(venues.is_open(11 * HOUR, 2 * HOUR, minute), expected)

    def test_always_open(self):
        for minute in (0, 3 * HOUR, 13 * HOUR, 23 * HOUR):
            with self.subTest(minute=minute):
                self.assertTrue(venues.is_open(-1, -1, minute))

    def test_hours_are_described_for_the_prompt(self):
        self.assertEqual(venues.describe_hours(8 * HOUR, 18 * HOUR), "08:00-18:00")
        self.assertEqual(venues.describe_hours(-1, -1), "always open")


class TestCommonality(unittest.TestCase):
    def test_a_hamlet_has_no_apothecary_but_may_have_a_shrine(self):
        self.assertFalse(venues.kind_allowed("apothecary", "hamlet"))
        self.assertTrue(venues.kind_allowed("shrine", "hamlet"))

    def test_a_counting_house_needs_a_city(self):
        self.assertFalse(venues.kind_allowed("counting_house", "town"))
        self.assertTrue(venues.kind_allowed("counting_house", "city"))

    def test_bigger_settlements_support_strictly_more(self):
        sizes = ("hamlet", "village", "town", "city")
        counts = [len(venues.plausible_kinds(size)) for size in sizes]
        self.assertEqual(counts, sorted(counts))
        self.assertLess(counts[0], counts[-1])


class _WorldCase(unittest.TestCase):
    """Each test gets a clean world; these touch the locations table directly."""

    def setUp(self) -> None:
        os.environ.update(_ENV)
        with connect() as conn:
            conn.execute("DELETE FROM npcs")
            conn.execute("UPDATE player SET current_location_id = NULL WHERE id = 1")
            conn.execute("DELETE FROM locations")
            self.square = world._upsert_location(conn, "Brimmer Square", "A market square in a busy town.")
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (self.square,))
            world._pacing_set(conn, "world_minute", 10 * HOUR)


class TestContainment(_WorldCase):
    def test_a_shop_named_on_a_square_becomes_a_child_of_it(self):
        with connect() as conn:
            shop = world._upsert_location(conn, "Brimmer Apothecary", "Jars and a counter.")
            row = world._location_row(conn, shop)
            self.assertEqual(int(row["parent_id"]), self.square)
            self.assertEqual(str(row["kind"]), "apothecary")
            self.assertEqual(int(row["open_minute"]), 8 * HOUR)

    def test_an_open_place_stays_top_level(self):
        with connect() as conn:
            road = world._upsert_location(conn, "East Road", "Out of town.")
            row = world._location_row(conn, road)
            self.assertEqual(int(row["parent_id"]), 0)
            self.assertEqual(str(row["kind"]), "")

    def test_venues_do_not_nest(self):
        """A shop named while the player is inside another shop belongs to the street."""
        with connect() as conn:
            shop = world._upsert_location(conn, "Brimmer Apothecary", "Jars.")
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (shop,))
            second = world._upsert_location(conn, "Brimmer Bakehouse", "Flour.")
            self.assertEqual(int(world._location_row(conn, second)["parent_id"]), self.square)

    def test_venues_at_reports_open_state(self):
        with connect() as conn:
            world._upsert_location(conn, "Brimmer Apothecary", "Jars.")
            world._pacing_set(conn, "world_minute", 20 * HOUR)
            listed = world.venues_at(conn, self.square)
            self.assertEqual(len(listed), 1)
            self.assertFalse(listed[0]["open"])
            self.assertIn("closed", listed[0]["hours"])


class TestEntryRules(_WorldCase):
    def test_entering_from_the_parent_is_allowed(self):
        with connect() as conn:
            shop = world._upsert_location(conn, "Brimmer Apothecary", "Jars.")
            gate = world.gate_venue_move(conn, self.square, shop)
            self.assertEqual(gate["location_id"], shop)
            self.assertIsNone(gate["note"])

    def test_entering_from_far_away_lands_at_the_parent_instead(self):
        """Was: walk from two locations away straight into the shop's interior."""
        with connect() as conn:
            shop = world._upsert_location(conn, "Brimmer Apothecary", "Jars.")
            road = world._upsert_location(conn, "East Road", "Out of town.")
            gate = world.gate_venue_move(conn, road, shop)
            self.assertEqual(gate["location_id"], self.square)
            self.assertEqual(gate["note"]["kind"], "venue_redirect")

    def test_a_closed_venue_cannot_be_entered(self):
        with connect() as conn:
            shop = world._upsert_location(conn, "Brimmer Apothecary", "Jars.")
            world._pacing_set(conn, "world_minute", 23 * HOUR)
            gate = world.gate_venue_move(conn, self.square, shop)
            self.assertEqual(gate["location_id"], self.square)
            self.assertEqual(gate["note"]["kind"], "venue_closed")

    def test_leaving_a_venue_is_never_blocked(self):
        with connect() as conn:
            shop = world._upsert_location(conn, "Brimmer Apothecary", "Jars.")
            gate = world.gate_venue_move(conn, shop, self.square)
            self.assertEqual(gate["location_id"], self.square)
            self.assertIsNone(gate["note"])

    def test_ordinary_travel_is_untouched(self):
        with connect() as conn:
            road = world._upsert_location(conn, "East Road", "Out of town.")
            gate = world.gate_venue_move(conn, self.square, road)
            self.assertEqual(gate["location_id"], road)
            self.assertIsNone(gate["note"])


class TestPlausibility(_WorldCase):
    def test_a_hamlet_does_not_grow_an_apothecary_on_request(self):
        with connect() as conn:
            camp = world._upsert_location(conn, "Kettle Camp", "A few tents by the road.")
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (camp,))
            got = world._upsert_location(conn, "Kettle Apothecary", "")
            self.assertEqual(got, camp, "player should simply find no such shop")
            self.assertIsNone(
                conn.execute("SELECT id FROM locations WHERE name = 'Kettle Apothecary'").fetchone()
            )

    def test_a_town_does_grow_one(self):
        with connect() as conn:
            got = world._upsert_location(conn, "Brimmer Apothecary", "")
            self.assertNotEqual(got, self.square)

    def test_capacity_per_kind_is_respected(self):
        with connect() as conn:
            first = world._upsert_location(conn, "Brimmer Apothecary", "")
            second = world._upsert_location(conn, "Wick Street Herbalist", "")
            self.assertNotIn(second, (self.square, first))
            # apothecary caps at 2 per settlement; the third finds no room
            third = world._upsert_location(conn, "Low Lane Chemist", "")
            self.assertEqual(third, self.square)


class TestDoorwayIsAMove(_WorldCase):
    """A doorway is the move the model narrates and reliably fails to record."""

    def test_entry_and_exit_phrases_are_detected(self):
        for text, expected in (
            ("I look around the square for an apothecary and step inside it.", "enter"),
            ("I go back inside the same apothecary.", "enter"),
            ("I duck into the alley", "enter"),
            ("I step back out of the apothecary onto the square.", "exit"),
            ("I leave the shop and go outside", "exit"),
        ):
            with self.subTest(text=text):
                self.assertEqual(world.venue_move_intent(text), expected)

    def test_common_phrases_are_not_doorways(self):
        """"in" and "out" as bare keywords made these all travel turns."""
        for text in (
            "I put the coin in my pocket",
            "I hand out the flyers",
            "I look in the crates",
            "I take the letter out of my bag",
            "I wait in the square",
            "I ask the merchant about taxes",
        ):
            with self.subTest(text=text):
                self.assertEqual(world.venue_move_intent(text), "")

    def test_entering_a_named_venue_is_repaired(self):
        with connect() as conn:
            shop = world._upsert_location(conn, "Brimmer Apothecary", "Jars.")
            result: dict = {"player": {}}
            report = world.resolve_movement(
                conn, result, "I go back inside the same apothecary.",
                intent="investigation", narration="You push the door open.",
            )
            self.assertEqual(report["rule"], "venue_enter")
            self.assertEqual(result["player"]["move_to_location"], "Brimmer Apothecary")
            self.assertEqual(world._find_location_id(conn, "Brimmer Apothecary"), shop)

    def test_stepping_out_returns_to_the_parent(self):
        with connect() as conn:
            shop = world._upsert_location(conn, "Brimmer Apothecary", "Jars.")
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (shop,))
            result: dict = {"player": {}}
            report = world.resolve_movement(
                conn, result, "I step back out onto the square.",
                intent="general", narration="The door swings shut behind you.",
            )
            self.assertEqual(report["rule"], "venue_exit")
            self.assertEqual(result["player"]["move_to_location"], "Brimmer Square")

    def test_a_first_visit_opens_the_shop_when_the_settlement_supports_it(self):
        with connect() as conn:
            result: dict = {"player": {}}
            report = world.resolve_movement(
                conn, result, "I look around the square for an apothecary and step inside it.",
                intent="investigation", narration="Shelves of jars line the walls.",
            )
            self.assertEqual(report["rule"], "venue_opened")
            row = world._location_row(conn, world._find_location_id(conn, report["destination"]))
            self.assertEqual(str(row["kind"]), "apothecary")
            self.assertEqual(int(row["parent_id"]), self.square)

    def test_a_first_visit_opens_nothing_the_settlement_cannot_support(self):
        with connect() as conn:
            camp = world._upsert_location(conn, "Kettle Camp", "A few tents by the road.")
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (camp,))
            result: dict = {"player": {}}
            report = world.resolve_movement(
                conn, result, "I step inside the apothecary.",
                intent="investigation", narration="",
            )
            self.assertNotEqual(report.get("rule"), "venue_opened")
            self.assertIsNone(
                conn.execute("SELECT id FROM locations WHERE kind = 'apothecary'").fetchone()
            )

    def test_returning_from_far_away_travels_to_the_shop_door(self):
        """The journey home happens this turn; going inside costs the next one."""
        with connect() as conn:
            shop = world._upsert_location(conn, "Brimmer Apothecary", "Jars.")
            conn.execute("UPDATE locations SET visit_count = 2 WHERE id = ?", (shop,))
            camp = world._upsert_location(conn, "Riverbend Camp", "Tents.")
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (camp,))
            result: dict = {"player": {}}
            report = world.resolve_movement(
                conn, result, "I head all the way back to that apothecary I visited earlier.",
                intent="travel", narration="You walk the road west.",
            )
            self.assertEqual(report["rule"], "venue_return")
            target = world._find_location_id(conn, result["player"]["move_to_location"])
            gate = world.gate_venue_move(conn, camp, target)
            self.assertEqual(gate["location_id"], self.square)
            self.assertEqual(gate["note"]["kind"], "venue_redirect")

    def test_only_the_players_words_can_open_a_venue(self):
        """Letting the narration mint venues would drop a shop wherever prose drifted."""
        with connect() as conn:
            self.assertEqual(
                world._mint_venue_from_request(conn, self.square, "I watch the crowd go by"), ""
            )


class TestKeeperIdentity(_WorldCase):
    def test_the_keeper_is_pinned_and_stays_pinned(self):
        with connect() as conn:
            shop = world._upsert_location(conn, "Brimmer Apothecary", "Jars.")
            conn.execute(
                "INSERT INTO npcs (code, location_id, name, race, role, summary, attitude, presence, shell) "
                "VALUES ('A', ?, 'Aria Fenn', 'human', 'apothecary', 'Keeps the shop.', 'friendly', 'present', 0)",
                (shop,),
            )
            first = world.bind_venue_keeper(conn, shop)
            self.assertTrue(first)
            # A later arrival must not take over the counter.
            conn.execute(
                "INSERT INTO npcs (code, location_id, name, race, role, summary, attitude, presence, shell) "
                "VALUES ('B', ?, 'Someone Else', 'human', 'customer', 'Browsing.', 'neutral', 'present', 0)",
                (shop,),
            )
            self.assertEqual(world.bind_venue_keeper(conn, shop), first)

    def test_an_open_place_has_no_keeper(self):
        with connect() as conn:
            self.assertEqual(world.bind_venue_keeper(conn, self.square), 0)


class TestStateAndContract(_WorldCase):
    def test_state_lists_what_can_be_entered_from_here(self):
        with connect() as conn:
            world._upsert_location(conn, "Brimmer Apothecary", "Jars.")
            world._upsert_location(conn, "East Road", "Out of town.")
        current = world.get_state(include_hidden=True)["current_location"]
        self.assertFalse(current["inside_venue"])
        self.assertEqual([v["name"] for v in current["venues_here"]], ["Brimmer Apothecary"])

    def test_inside_a_venue_the_state_names_the_way_out(self):
        with connect() as conn:
            shop = world._upsert_location(conn, "Brimmer Apothecary", "Jars.")
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (shop,))
        current = world.get_state(include_hidden=True)["current_location"]
        self.assertTrue(current["inside_venue"])
        self.assertEqual(current["exit_to"], "Brimmer Square")

    def test_contract_separates_travel_destinations_from_interiors(self):
        """An interior in known_places invited travel straight into a shop."""
        with connect() as conn:
            world._upsert_location(conn, "Brimmer Apothecary", "Jars.")
            world._upsert_location(conn, "East Road", "Out of town.")
        state = world.get_state(include_hidden=True)
        contract = world.movement_contract(state, "I look around", "investigate")
        self.assertIn("East Road", contract["known_places"])
        self.assertNotIn("Brimmer Apothecary", contract["known_places"])
        self.assertEqual([v["name"] for v in contract["venues_here"]], ["Brimmer Apothecary"])

    def test_contract_names_what_is_shut(self):
        with connect() as conn:
            world._upsert_location(conn, "Brimmer Apothecary", "Jars.")
            world._pacing_set(conn, "world_minute", 23 * HOUR)
        contract = world.movement_contract(
            world.get_state(include_hidden=True), "I look around", "investigate"
        )
        self.assertEqual(contract.get("closed_now"), ["Brimmer Apothecary"])


class TestMigration(unittest.TestCase):
    def test_a_pre_venue_database_gains_the_columns_without_losing_rows(self):
        older = Path(tempfile.mkdtemp(prefix="morkyn-oldsave-")) / "old.db"
        conn = sqlite3.connect(older)
        conn.executescript(
            """
            CREATE TABLE locations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE DEFAULT '',
                name TEXT NOT NULL UNIQUE,
                summary TEXT NOT NULL DEFAULT '',
                discovered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                visit_count INTEGER NOT NULL DEFAULT 0);
            INSERT INTO locations (code, name, summary, visit_count)
            VALUES ('L1', 'Old Town', 'Pre-existing.', 7);
            """
        )
        conn.commit()
        conn.close()

        previous = os.environ["AI_RPG_DB"]
        os.environ["AI_RPG_DB"] = str(older)
        try:
            init_db()
            with connect() as migrated:
                columns = {row[1] for row in migrated.execute("PRAGMA table_info(locations)")}
                row = migrated.execute(
                    "SELECT name, visit_count, parent_id, kind, open_minute FROM locations"
                ).fetchone()
        finally:
            os.environ["AI_RPG_DB"] = previous

        self.assertTrue({"parent_id", "kind", "open_minute", "close_minute",
                         "settlement_size", "keeper_npc_id"} <= columns)
        self.assertEqual(row["name"], "Old Town")
        self.assertEqual(row["visit_count"], 7)
        self.assertEqual(row["parent_id"], 0)
        self.assertEqual(row["open_minute"], -1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
