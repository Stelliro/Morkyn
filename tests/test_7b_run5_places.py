"""Place fixes from the fifth Saltmarrow run on Qwen2.5 7B (playtest #127, #128, #136)."""
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-7b-run5-places-"))
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


def seed(here: int = 1) -> None:
    """Saltmarrow (a town) with its salvage yard, and the wreck out on the flats."""
    from app import db
    from app.db import connect

    db.init_db()
    with connect() as conn:
        conn.execute("UPDATE player SET current_location_id = 1 WHERE id = 1")
        conn.execute("DELETE FROM npcs")
        conn.execute("DELETE FROM locations WHERE id != 1")
        conn.execute(
            "UPDATE locations SET code = 'L1', name = 'Saltmarrow', summary = 'A drowned harbour town.', parent_id = 0, "
            "kind = '', settlement_size = 'town', keeper_npc_id = 0 WHERE id = 1"
        )
        conn.execute(
            "INSERT INTO locations (id, code, name, summary, parent_id, kind) "
            "VALUES (2, 'L2', 'Saltmarrow Salvage Yard', 'A yard filled with crates.', 1, 'salvage_yard')"
        )
        conn.execute(
            "INSERT INTO locations (id, code, name, summary) VALUES (4, 'L4', 'Wrecked Ship', 'A wreck on the flats.')"
        )
        conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (here,))


def add_inn(conn, name: str = "The Blind Pike", parent: int = 1) -> int:
    cur = conn.execute(
        "INSERT INTO locations (code, name, summary, parent_id, kind) VALUES (?, ?, 'A modest inn.', ?, 'inn')",
        (f"L{100 + parent}{len(name)}", name, parent),
    )
    return int(cur.lastrowid)


class FurnitureIsNotAPlace(unittest.TestCase):
    """T24/T34/T50: 'your bed' became the place 'Your Bed' and the save moved the player into it."""

    def test_names(self):
        from app.world import is_plausible_place_name

        for name in ("your bed", "Your Bed", "my cot", "the cot", "Bed", "her room"):
            with self.subTest(name=name):
                self.assertFalse(is_plausible_place_name(name))
        for name in ("The Long Table", "The Blind Pike", "Saltmarrow Salvage Yard", "Bedford"):
            with self.subTest(name=name):
                self.assertTrue(is_plausible_place_name(name))

    def test_not_minted(self):
        from app.db import connect
        from app.world import _upsert_location

        seed()
        with connect() as conn:
            got = _upsert_location(conn, "your bed", "You lie down on a rough mattress in the back of the inn.")
            count = conn.execute("SELECT COUNT(*) FROM locations").fetchone()[0]
        self.assertEqual((got, count), (1, 3))

    def test_a_move_to_an_old_bed_row_is_dropped(self):
        from app import world
        from app.db import connect

        seed(here=4)
        with connect() as conn:
            conn.execute("INSERT INTO locations (id, code, name, summary) VALUES (8, 'L8', 'Your Bed', '')")
            line = 'I tell them, "I\'m going out to the wreck now." Then I walk out toward the cove.'
            prose = "You walk out toward the cove, the fog thick over the flats."
            result = {"narration": prose, "player": {"move_to_location_code": "L8"}}
            report = world.resolve_movement(conn, result, line, intent="travel", narration=prose)
        self.assertNotEqual(result["player"].get("move_to_location_code"), "L8")
        self.assertNotEqual(report.get("destination"), "L8")


class AnInnInTownIsAVenue(unittest.TestCase):
    """T22/T23/T61: 'The Blind Pike', 'A modest inn ...', was minted as a second town."""

    def test_described_inn_stands_in_the_town(self):
        from app.db import connect
        from app.world import _location_row, _upsert_location

        seed()
        with connect() as conn:
            new_id = _upsert_location(conn, "The Blind Pike", "A modest inn with a smoke-filled common area.")
            row = _location_row(conn, new_id)
        self.assertEqual((int(row["parent_id"]), row["kind"]), (1, "inn"))

    def test_far_or_plain_places_stay_open_ground(self):
        from app.db import connect
        from app.world import _location_row, _upsert_location

        seed()
        with connect() as conn:
            far = _location_row(conn, _upsert_location(conn, "The Drowned Rat", "A ruined inn far out on the moor."))
            plain = _location_row(conn, _upsert_location(conn, "Coast Road", "A muddy road along the flats."))
        self.assertEqual((int(far["parent_id"]), far["kind"]), (0, ""))
        self.assertEqual((int(plain["parent_id"]), plain["kind"]), (0, ""))


class OneInnOneRow(unittest.TestCase):
    """#136: one inn became 'The Blind Pike', 'The Blind Pike Tavern' and 'Saltmarrow Tavern'."""

    def test_kind_words_on_a_known_name(self):
        from app import turn_ledger
        from app.db import connect
        from app.world import _upsert_location

        seed()
        notes = []

        @turn_ledger.recorded("turn")
        def go():
            with connect() as conn:
                inn = add_inn(conn)
                got = (
                    inn,
                    _upsert_location(conn, "The Blind Pike Tavern", ""),
                    _upsert_location(conn, "Saltmarrow Tavern", ""),
                    _upsert_location(conn, "the Blind Pike Inn", ""),
                )
            notes.extend(turn_ledger.current().notes)
            return got

        inn, tavern, town_tavern, inn_again = go()
        self.assertEqual({tavern, town_tavern, inn_again}, {inn})
        self.assertTrue(any(n["decision"] == "resolved_to_known" for n in notes))

    def test_two_inns_leave_the_town_name_alone(self):
        from app.db import connect
        from app.world import _upsert_location

        seed()
        with connect() as conn:
            a = add_inn(conn, "The Blind Pike")
            b = add_inn(conn, "The Salt Cellar")
            got = _upsert_location(conn, "Saltmarrow Tavern", "")
        self.assertNotIn(got, {a, b})

    def test_the_tavern_the_player_walks_into_is_the_inn(self):
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            inn = add_inn(conn)
            for line in (
                "I go into the Blind Pike Tavern, find Verity behind the bar and ask for the same room.",
                "I go into the tavern and ask for a room.",
            ):
                with self.subTest(line=line):
                    prose = "You push the door open and step inside, the common room warm and smoky."
                    result = {"narration": prose, "player": {}}
                    report = world.resolve_movement(conn, result, line, intent="travel", narration=prose)
                    self.assertEqual(report.get("destination"), "The Blind Pike", report)
            count = conn.execute("SELECT COUNT(*) FROM locations").fetchone()[0]
        self.assertEqual(count, 4)
        self.assertTrue(inn)


class GluedNamesResolve(unittest.TestCase):
    """#128: 'The Blind Pike Salvage Yard' was minted under the inn and preferred over the real yard."""

    def test_glued_to_the_yard(self):
        from app.db import connect
        from app.world import _upsert_location

        seed()
        with connect() as conn:
            add_inn(conn)
            got = _upsert_location(conn, "The Blind Pike Salvage Yard", "A cluttered space filled with salvaged goods.")
        self.assertEqual(got, 2)

    def test_another_towns_market_is_not_ours(self):
        from app.db import connect
        from app.world import _upsert_location

        seed()
        with connect() as conn:
            conn.execute("INSERT INTO locations (id, code, name, summary) VALUES (5, 'L5', 'Rivertown', '')")
            conn.execute(
                "INSERT INTO locations (id, code, name, summary, parent_id) "
                "VALUES (6, 'L6', 'Rivertown Fish Market', '', 5)"
            )
            got = _upsert_location(conn, "Saltmarrow Fish Market", "")
        self.assertNotIn(got, {5, 6, 1})


class TheMisspeltTownIsTheTown(unittest.TestCase):
    """T15: 'head back across the flats to Saltmarrow' minted 'Salammar'."""

    def test_only_beside_the_players_word(self):
        from app.db import connect
        from app.world import _known_place_misspelt

        seed(here=4)
        line = "The tide's due. I get up and head back across the flats to Saltmarrow before the water comes in."
        with connect() as conn:
            hit = _known_place_misspelt(conn, "Salammar", line)
            self.assertEqual(int(hit["id"]), 1)
            self.assertIsNone(_known_place_misspelt(conn, "Salammar", "I head back across the flats."))
            self.assertIsNone(_known_place_misspelt(conn, "Saltmarsh Ferry", line))

    def test_the_players_named_place_beats_an_unshown_move(self):
        from app import world
        from app.db import connect

        seed(here=4)
        line = "The tide's due. I check the reckoner, get up and head back across the flats to Saltmarrow."
        prose = "You head back towards the settlement of Salammar, keeping to the firm ground. You reach the outskirts."
        result = {
            "narration": prose,
            "player": {"move_to_location": "The Candle at Wrecked"},
            "locations": [{"name": "Salammar", "summary": "a bustling settlement on the coast"}],
        }
        with connect() as conn:
            report = world.resolve_movement(conn, result, line, intent="travel", narration=prose)
        self.assertEqual((report["rule"], report["destination"]), ("player_named", "Saltmarrow"))
        self.assertEqual(result["player"]["move_to_location_code"], "L1")

    def test_apply_keeps_one_town_and_spells_it_right(self):
        from app import world
        from app.db import connect

        seed(here=4)
        line = "The tide's due. I get up and head back across the flats to Saltmarrow before the water comes in."
        prose = "You head back towards Salammar across the ridges. You reach the outskirts of Salammar at last."
        result = {
            "narration": prose,
            "player": {"move_to_location_code": "L1"},
            "locations": [{"name": "Salammar", "summary": "a bustling settlement on the coast"}],
        }
        world.apply_turn(result, line, prompt_context={})
        with connect() as conn:
            names = [r[0] for r in conn.execute("SELECT name FROM locations")]
            here = conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()[0]
            told = conn.execute("SELECT content FROM journal WHERE kind = 'narration' ORDER BY id DESC LIMIT 1").fetchone()
        self.assertNotIn("Salammar", names)
        self.assertEqual(here, 1)
        self.assertNotIn("Salammar", world._narration_text(result))
        self.assertIn("Saltmarrow", world._narration_text(result))
        if told is not None:
            self.assertNotIn("Salammar", told[0])

    def test_a_move_the_prose_shows_stands(self):
        from app import world
        from app.db import connect

        seed(here=4)
        line = "I walk back to Saltmarrow and on to the salvage yard."
        prose = "You cross the flats into Saltmarrow and walk on into the Saltmarrow Salvage Yard."
        result = {"narration": prose, "player": {"move_to_location": "Saltmarrow Salvage Yard"}}
        with connect() as conn:
            report = world.resolve_movement(conn, result, line, intent="travel", narration=prose)
        self.assertNotEqual(report.get("rule"), "player_named")


class QuestionsAndDenialsAreNotDestinations(unittest.TestCase):
    """T60: 'Shouldn't you be at the Blind Pike?' moved the player; T86: 'not the yard' ended in the yard."""

    def test_destination_text(self):
        from app.world import _destination_text

        text = _destination_text(
            '"Warin, why are you out here? Shouldn\'t you be at the Blind Pike?" I search the upstairs rooms.'
        )
        self.assertNotIn("blind pike", text.lower())
        self.assertIn("blind pike", _destination_text("Can we go to the Blind Pike?").lower())
        self.assertIn("blind pike", _destination_text("Why don't we go to the Blind Pike?").lower())
        self.assertNotIn("yard", _destination_text("I'm in the town square, not the yard. I walk to the flats.").lower())
        self.assertIn("mill", _destination_text("I'm not sure, but I head for the mill.").lower())

    def test_question_moves_nobody(self):
        from app import world
        from app.db import connect

        seed(here=4)
        with connect() as conn:
            add_inn(conn)
            line = '"Warin, why are you out here? Shouldn\'t you be at the Blind Pike?" I search the upstairs rooms.'
            prose = "You climb the stairs and search the upstairs rooms."
            result = {"narration": prose, "player": {}}
            report = world.resolve_movement(conn, result, line, intent="travel", narration=prose)
        self.assertNotEqual(report.get("destination"), "The Blind Pike")

    def test_denied_yard_and_origin_code(self):
        from app import world
        from app.db import connect

        seed(here=1)
        line = "I'm in the town square, not the yard. I walk to the edge of the flats and practise with the reckoner."
        prose = (
            "You walk from the Saltmarrow Salvage Yard [[L2]] to the town square. You reach the edge of the flats "
            "and spend an hour practising."
        )
        with connect() as conn:
            result = {"narration": prose, "player": {}}
            report = world.resolve_movement(conn, result, line, intent="travel", narration=prose)
            self.assertNotEqual(result["player"].get("move_to_location_code"), "L2", report)
            explicit = {"narration": prose, "player": {"move_to_location_code": "L2"}}
            world.resolve_movement(conn, explicit, line, intent="travel", narration=prose)
            self.assertNotEqual(explicit["player"].get("move_to_location_code"), "L2")

    def test_code_is_origin(self):
        from app.world import _code_is_origin

        def check(text):
            i = text.index("[[")
            return _code_is_origin(text, i, text.index("]]") + 2)

        self.assertTrue(check("You walk from the Saltmarrow Salvage Yard [[L2]] to the town square."))
        self.assertTrue(check("The Blind Pike Salvage Yard [[L9]] fades behind you, and you step onto the path."))
        self.assertFalse(check("You leave the yard and walk into the Blind Pike [[L7]]."))
        self.assertFalse(check("At last you reach the Blind Pike [[L7]]."))


if __name__ == "__main__":
    unittest.main()
