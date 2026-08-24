"""Regression tests: the map stops growing copies of the place you are standing in.

Two shapes survived every existing guard, both replayed here from the location
tables six recorded 100-turn runs actually left behind:

    Mosswake Gate
    Hills Beyond Mosswake Gate
    Hills Beyond Mosswake Gate Eastward   <- a bearing, not a new place
    ...
    Riverbend Camp
    Riverbend                             <- the stem, minted a second time

`_place_extension_target` already merged a generic tail noun onto a leading
prefix ("Riverbend Hillcrest" + "Camp"), but its tail list held no bearings, so
adding "Eastward" opened a row. And nothing looked the other way at all: when
the model dropped the qualifier instead of adding one, the bare stem became its
own place beside the full name.

Separately, a live space-opera run spent three of six turns at a location
literally named `[[L1]]` -- the entity-code wrapper answered as a destination.
`is_plausible_person_name` had refused bare codes for a while; places never did.

Run:  python -m unittest tests.test_place_name_accretion
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-place-test-"))
_ENV = {
    "AI_RPG_DB": str(_TMP / "world.db"),
    "AI_RPG_PACK_DIR": str(_TMP / "packs"),
    "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
    "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
    "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
    "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
}
os.environ.update(_ENV)

from app import world  # noqa: E402
from app.db import connect, db_path, init_db  # noqa: E402


def _assert_isolated() -> None:
    if not str(db_path()).startswith(str(_TMP)):
        raise AssertionError(f"test isolation failed: AI_RPG_DB is {db_path()!r}")


def setUpModule() -> None:
    os.environ.update(_ENV)
    _assert_isolated()


_assert_isolated()
init_db()


def _seed_player(conn) -> None:
    """Minimal valid player row, whatever NOT NULL columns the schema carries."""
    cols = {r["name"]: r for r in conn.execute("PRAGMA table_info(player)")}
    values = {
        name: (0 if str(row["type"]).upper() in {"INTEGER", "REAL"} else "")
        for name, row in cols.items()
        if row["notnull"] and row["dflt_value"] is None and name != "id"
    }
    values["name"] = "Tester"
    keys = ", ".join(["id", *values])
    marks = ", ".join(["?"] * (1 + len(values)))
    conn.execute(f"INSERT OR REPLACE INTO player ({keys}) VALUES ({marks})", (1, *values.values()))


class PlaceCase(unittest.TestCase):
    def setUp(self):
        with connect() as conn:
            conn.execute("UPDATE player SET current_location_id = NULL")
            conn.execute("DELETE FROM locations")
            _seed_player(conn)

    def _add(self, *names: str) -> list[str]:
        """Upsert each name in order; return the final map."""
        with connect() as conn:
            for name in names:
                world._upsert_location(conn, name)
            return [r["name"] for r in conn.execute("SELECT name FROM locations ORDER BY id")]


class TestBearingsAreNotNewPlaces(PlaceCase):
    def test_eastward_does_not_open_a_second_row(self):
        self.assertEqual(
            self._add("Hills Beyond Mosswake Gate", "Hills Beyond Mosswake Gate Eastward"),
            ["Hills Beyond Mosswake Gate"],
        )

    def test_a_storey_does_not_open_a_second_row(self):
        # Recorded in the post-apocalyptic genre run.
        self.assertEqual(
            self._add("Abandoned Water Structure", "Abandoned Water Structure Lower Level"),
            ["Abandoned Water Structure"],
        )

    def test_a_distinctive_addition_is_still_its_own_place(self):
        # "market" is not generic, so the square keeps its row.
        self.assertEqual(
            self._add("Mosswake Gate", "Mosswake Gate Market Square"),
            ["Mosswake Gate", "Mosswake Gate Market Square"],
        )

    def test_an_unrelated_name_is_untouched(self):
        self.assertEqual(
            self._add("Mosswake Gate", "Redmill Ford"), ["Mosswake Gate", "Redmill Ford"]
        )


class TestTheBareStem(PlaceCase):
    def test_the_stem_of_one_existing_place_is_that_place(self):
        self.assertEqual(self._add("Riverbend Camp", "Riverbend"), ["Riverbend Camp"])

    def test_the_stem_of_a_gate_is_that_gate(self):
        self.assertEqual(self._add("Mosswake Gate", "Mosswake"), ["Mosswake Gate"])

    def test_an_ambiguous_stem_keeps_its_own_row(self):
        # "Riverbend" names the area, not the camp or the ford. Picking one
        # would move the player somewhere they never walked.
        self.assertEqual(
            self._add("Riverbend Camp", "Riverbend Gate", "Riverbend"),
            ["Riverbend Camp", "Riverbend Gate", "Riverbend"],
        )

    def test_a_stem_of_a_distinctive_name_keeps_its_own_row(self):
        # "hillcrest" is not a generic tail, so "Riverbend" is not merely it.
        self.assertEqual(
            self._add("Riverbend Hillcrest", "Riverbend"),
            ["Riverbend Hillcrest", "Riverbend"],
        )

    def test_the_existing_extension_guard_still_works(self):
        self.assertEqual(
            self._add("Riverbend Hillcrest", "Riverbend Hillcrest Camp", "Riverbend Hillcrest Post"),
            ["Riverbend Hillcrest"],
        )


class TestEntityCodesAreNotPlaces(PlaceCase):
    def test_a_wrapped_code_is_unwrapped(self):
        for raw, want in (
            ("[[L1]]", "L1"),
            ("[L1]", "L1"),
            ("((L1))", "L1"),
            ("[[C]]", "C"),
        ):
            with self.subTest(raw=raw):
                self.assertEqual(world.humanize_place_name(raw), want)

    def test_a_wrapped_real_name_survives_unwrapping(self):
        # And therefore matches the row that already holds it.
        self.assertEqual(world.humanize_place_name("[[Mosswake Gate]]"), "Mosswake Gate")
        self.assertEqual(self._add("Mosswake Gate", "[[Mosswake Gate]]"), ["Mosswake Gate"])

    def test_bare_codes_are_refused_as_place_names(self):
        for code in ("L1", "L12", "E3", "I2", "NPC2", "AA", "[[L1]]", "[[NPC2]]"):
            with self.subTest(code=code):
                self.assertFalse(
                    world.is_plausible_place_name(world.humanize_place_name(code)),
                    f"{code!r} was accepted as a toponym",
                )

    def test_short_real_place_names_still_pass(self):
        for name in ("Ys", "Oz", "Rio", "The Salt Crow", "Docking Bay Seven", "Mosswake Gate"):
            with self.subTest(name=name):
                self.assertTrue(world.is_plausible_place_name(name))

    def test_a_code_does_not_become_a_row(self):
        with connect() as conn:
            here = world._upsert_location(conn, "Docking Bay Seven")
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (here,))
            landed = world._upsert_location(conn, "[[L1]]")
            names = [r["name"] for r in conn.execute("SELECT name FROM locations ORDER BY id")]
        self.assertEqual(names, ["Docking Bay Seven"])
        self.assertEqual(landed, here)


class TestPossessiveChains(PlaceCase):
    """One possessive is a toponym. Two is the model walking into its own phrase.

    Recorded live in a high-fantasy run, once the prompt stopped handing it
    somebody else's river to escape to:

        The Sunken Colonnade
        The Sunken Colonnade's Shadow
        The Sunken Colonnade's Shadow's Heart
        The Sunken Colonnade's Shadow's Heart Passage

    Four rows for one place, the deepest unsayable. The token-prefix guard
    cannot see it -- "colonnade's" is not the token "colonnade", so as far as
    `_place_extension_target` is concerned the names share no prefix at all.
    """

    def test_the_recorded_chain_folds_back(self):
        self.assertEqual(
            self._add(
                "The Sunken Colonnade",
                "The Sunken Colonnade's Shadow",
                "The Sunken Colonnade's Shadow's Heart",
                "The Sunken Colonnade's Shadow's Heart Passage",
            ),
            ["The Sunken Colonnade", "The Sunken Colonnade's Shadow"],
        )

    def test_one_possessive_is_a_real_sub_place(self):
        self.assertEqual(
            self._add("The Sunken Colonnade", "The Sunken Colonnade's Shadow"),
            ["The Sunken Colonnade", "The Sunken Colonnade's Shadow"],
        )

    def test_ordinary_possessive_toponyms_survive(self):
        # Both recorded in live runs, both genuine places.
        self.assertEqual(
            self._add("Deadman's Hollow", "The Water's Edge Camp"),
            ["Deadman's Hollow", "The Water's Edge Camp"],
        )

    def test_a_chain_with_nothing_to_fold_into_is_kept(self):
        # Refusing a name outright is not this guard's job. With no existing
        # prefix there is no row to join, so a florid opening name stands.
        self.assertEqual(
            self._add("The Lord's Keeper's Tower"), ["The Lord's Keeper's Tower"]
        )

    def test_a_curly_apostrophe_counts(self):
        self.assertEqual(
            self._add(
                "The Sunken Colonnade",
                "The Sunken Colonnade\u2019s Shadow",
                "The Sunken Colonnade\u2019s Shadow\u2019s Heart",
            ),
            ["The Sunken Colonnade", "The Sunken Colonnade\u2019s Shadow"],
        )

    def test_an_unrelated_double_possessive_is_untouched(self):
        self.assertEqual(
            self._add("Mosswake Gate", "The Miller's Widow's Yard"),
            ["Mosswake Gate", "The Miller's Widow's Yard"],
        )


if __name__ == "__main__":
    unittest.main()
