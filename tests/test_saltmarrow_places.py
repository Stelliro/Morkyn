"""Places, movement and people from the Saltmarrow API-bridge run.

#76  MOVE dropped on talk turns whose prose travelled; parentless places
     redirected every walk into a shop; a place named in passing was walked into.
#33  LOC_NEW places minted with no parent; a refused landmark renamed "Nearby street".
#112 Quoted speech and nouns ("the tally board") read as travel.
#113 Shop hours locked out the household.
#27  Every NPC got an invented "<Name>'s <shop>" workplace.
#73  Unshown strangers seeded into scenes; wait shells kept as standing people.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-saltmarrow-places-"))
_ENV = isolated_data_env(str(_TMP))
os.environ.update(_ENV)

from app import db, world  # noqa: E402
from app.db import connect  # noqa: E402

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


def seed_saltmarrow() -> None:
    """Saltmarrow (L1, start), the chandlery inside it (L2, kept by Philippa), a lone sea tower (L3)."""
    db.init_db()
    with connect() as conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("DELETE FROM npcs")
        conn.execute("DELETE FROM locations WHERE id != 1")
        conn.execute("DELETE FROM settings WHERE key IN ('active_scene', 'conversation', 'scene_thread')")
        conn.execute(
            "UPDATE locations SET code = 'L1', name = 'Saltmarrow', summary = 'Starting location.', parent_id = 0, "
            "kind = '', settlement_size = '', keeper_npc_id = 0 WHERE id = 1"
        )
        conn.execute(
            "INSERT INTO locations (id, code, name, summary, visit_count, parent_id, kind, open_minute, close_minute) "
            "VALUES (2, 'L2', 'Philippa Kemp''s General Store', 'Where Philippa works.', 2, 1, 'general_store', 420, 1140)"
        )
        conn.execute(
            "INSERT INTO locations (id, code, name, summary, visit_count, parent_id, kind) "
            "VALUES (3, 'L3', 'The Customs Tower', 'A square stone tower alone in the open sea.', 1, 0, '')"
        )
        conn.execute("INSERT INTO npcs (id, code, location_id, name, role, attitude) VALUES (1, 'A', 2, 'Philippa Kemp', 'chandler', 'neutral')")
        conn.execute("UPDATE locations SET keeper_npc_id = 1 WHERE id = 2")
        conn.execute("UPDATE player SET current_location_id = 1 WHERE id = 1")


class TravelWordsInSpeechOrNouns(unittest.TestCase):
    """#112."""

    def test_quoted_question_is_not_travel(self):
        line = '"No boy with a cart, not on my stretch," I tell Philippa. "Which channel did Tam take, and when did he leave?"'
        self.assertFalse(world.travel_intent(line))
        self.assertFalse(world.travel_intent('I hold on to her. "I\'m here, Mam. I\'m not going anywhere."'))

    def test_nouns_are_not_moves(self):
        self.assertFalse(world.travel_intent('I hand Mam the charcoal. "Tell them yourself, Mam. On the board."'))
        self.assertFalse(world.travel_intent("Tam and I walk the line round the bollard a turn at a time."))

    def test_real_moves_still_travel(self):
        self.assertTrue(world.travel_intent("I go along the wall to Philippa's chandlery."))
        self.assertTrue(world.travel_intent("I climb the iron ladder up to the first window of the customs tower and go in."))


class TalkTurnMovesStand(unittest.TestCase):
    """#76: the prose travelled, the MOVE was dropped."""

    def _gate(self, line, dest, narration):
        return world._unasked_unshown_move({"map_walk": None}, {"move_to_location": dest}, [], line, intent="conversation", narration=narration)

    def test_asked_for_in_the_players_words(self):
        line = 'I take the cart-hooks down to Hereward\'s skiff. "Hereward. Row me out to the old fish market?"'
        prose = "He takes the oars. The rows go by. The fish market's long humped roof rises out of the water ahead."
        self.assertEqual(self._gate(line, "The Old Fish Market", prose), "")

    def test_shown_by_a_shorter_name(self):
        line = "As Jocosa poles us out toward the tower, I keep my feet in and watch the water."
        prose = "Jocosa stops trying to find bottom and uses the pole as a paddle. The tower comes up out of the rain."
        self.assertEqual(self._gate(line, "the customs tower", prose), "")

    def test_unshown_unasked_move_still_dropped(self):
        line = '"Who runs the inn?" I ask.'
        prose = "Mara shrugs and keeps mending the net by the fire."
        self.assertEqual(self._gate(line, "The Old Well", prose), "The Old Well")


class LandmarkNames(unittest.TestCase):
    """#76/#33: "the Lantern Wives' lamp" was refused and renamed "Nearby street"."""

    def test_named_landmark_is_a_place(self):
        self.assertTrue(world.is_plausible_place_name("the Lantern Wives' lamp"))
        self.assertFalse(world.is_plausible_place_name("the old lamp"))
        self.assertFalse(world.is_plausible_place_name("Sky-crack first window"))

    def test_refused_place_is_dropped_not_renamed(self):
        from app import llm

        turn = {"narration": "", "locations": [{"name": "System pings a local job", "summary": "x"}]}
        out = llm._repair_entity_names_in_turn(turn, {"current_location": {"name": "Saltmarrow"}})
        self.assertEqual(out.get("locations"), [])


class PlaceNamedInPassing(unittest.TestCase):
    """#76 T4 and #33."""

    def setUp(self):
        seed_saltmarrow()

    def test_named_in_passing_is_not_where_you_went(self):
        prose = "Up close you can read it: one bronze bell, to be brought to the tally house whole."
        self.assertFalse(world._new_place_reached("the tally house", prose, "I go to the tally board and ask about the customs-house bell."))
        self.assertTrue(world._new_place_reached("the tally house", "You step into the tally house out of the wind.", "I wait."))

    def test_place_beside_here_gets_the_settlement_as_parent(self):
        with connect() as conn:
            new_id = world._upsert_location(conn, "The Tally House", "The guild's office on the harbour wall beside the tally board.")
            world._settle_place_named_in_passing(
                conn, new_id, "The Tally House", "The guild's office on the harbour wall beside the tally board.",
                {"player": {}}, {"status": "not_travel", "from": "L1"},
            )
            self.assertEqual(int(world._location_row(conn, new_id)["parent_id"]), 1)
            # From there the chandlery next door is reachable: no redirect onto the street.
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (new_id,))
            check = world.venue_entry_check(conn, new_id, world._location_row(conn, 2), world_minute=600)
            self.assertTrue(check["ok"], check)

    def test_far_place_or_destination_keeps_its_own_standing(self):
        with connect() as conn:
            far = world._upsert_location(conn, "The Drowned Bell", "A bell buoy beyond the last rows, out at sea, beside a wreck.")
            world._settle_place_named_in_passing(conn, far, "The Drowned Bell", "A bell buoy beyond the last rows, out at sea, beside a wreck.", {"player": {}}, {"from": "L1"})
            self.assertEqual(int(world._location_row(conn, far)["parent_id"] or 0), 0)
            went = world._upsert_location(conn, "The Net Loft", "A loft beside the harbour stairs.")
            world._settle_place_named_in_passing(
                conn, went, "The Net Loft", "A loft beside the harbour stairs.", {"player": {"move_to_location": "The Net Loft"}}, {"from": "L1"}
            )
            self.assertEqual(int(world._location_row(conn, went)["parent_id"] or 0), 0)


class HouseholdAfterHours(unittest.TestCase):
    """#113."""

    def setUp(self):
        seed_saltmarrow()

    def test_keeper_at_home_lets_a_known_face_in(self):
        with connect() as conn:
            check = world.venue_entry_check(conn, 1, world._location_row(conn, 2), world_minute=6 * 60 + 48)
        self.assertTrue(check["ok"], check)
        self.assertEqual(check["reason"], "after_hours")

    def test_strangers_and_unwelcome_still_wait(self):
        with connect() as conn:
            conn.execute("UPDATE locations SET visit_count = 0 WHERE id = 2")
            self.assertEqual(world.venue_entry_check(conn, 1, world._location_row(conn, 2), world_minute=400)["reason"], "closed")
            conn.execute("UPDATE locations SET visit_count = 3 WHERE id = 2")
            conn.execute("UPDATE npcs SET attitude = 'hostile' WHERE id = 1")
            self.assertEqual(world.venue_entry_check(conn, 1, world._location_row(conn, 2), world_minute=400)["reason"], "closed")


class WorkplacesFromTheRealTrade(unittest.TestCase):
    """#27."""

    def setUp(self):
        seed_saltmarrow()

    def _plan(self, role, location_id=1):
        import json

        with connect() as conn:
            conn.execute("DELETE FROM npcs WHERE id > 1")
            conn.execute("INSERT INTO npcs (id, code, location_id, name, role) VALUES (9, 'Z', ?, 'Wat Cooper', ?)", (location_id, role))
            world.plan_npc_workplace(conn, 9)
            row = conn.execute("SELECT workplace_plan, workplace_id FROM npcs WHERE id = 9").fetchone()
        return json.loads(row["workplace_plan"] or "{}"), int(row["workplace_id"] or 0)

    def test_no_shop_for_weavers_clerks_or_salvagers(self):
        for role in ("weaver", "tally clerk", "clerk", "salvager"):
            self.assertEqual(self._plan(role), ({}, 0), role)

    def test_a_real_trade_still_plans_premises(self):
        plan, _ = self._plan("baker")
        self.assertEqual(plan.get("kind"), "bakery")

    def test_no_premises_on_a_lone_tower(self):
        self.assertEqual(self._plan("baker", location_id=3), ({}, 0))


class StrangersOnlyWhereShown(unittest.TestCase):
    """#73."""

    def setUp(self):
        seed_saltmarrow()

    def test_role_comes_from_the_prose(self):
        sentence = "She steps past you to the next runner, a broad man with a split lip."
        with connect() as conn:
            self.assertEqual(world._seed_role_for(conn, 1, "a broad man", 0, salt="x", salt_sentence=sentence), "runner")
            self.assertEqual(world._seed_role_for(conn, 3, "a woman", 0, salt="x", salt_sentence="There is a woman beside it."), "local")

    def test_known_speaker_elsewhere_seeds_nobody(self):
        prose = 'Tam [[H]] braces his feet on the chimney. "Hold it," he says. "Just hold it, I can\'t feel my hands."'
        with connect() as conn:
            conn.execute("INSERT INTO npcs (id, code, location_id, name, role) VALUES (8, 'H', 2, 'Tam Kemp', 'carter')")
            made = world._ensure_npcs_from_narration(conn, {"npcs": []}, prose, 3)
            self.assertEqual(made, [])
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM npcs WHERE location_id = 3").fetchone()[0], 0)

    def test_wait_crowd_needs_a_settlement(self):
        with connect() as conn:
            self.assertFalse(world._in_settlement(conn, 3))
            self.assertTrue(world._in_settlement(conn, 2))
        self.assertIn("pickpocket_attempt", world._CROWD_WAIT_KINDS)
        self.assertIn("weather_shift", world._FACELESS_WAIT_KINDS)

    def test_cast_off_takes_a_minor_face_away(self):
        with connect() as conn:
            conn.execute(
                "INSERT INTO npcs (id, code, location_id, name, role, presence) VALUES (7, 'G', 2, 'Reinald', 'apprentice', 'event_worthy')"
            )
            conn.execute("UPDATE player SET current_location_id = 2 WHERE id = 1")
            self.assertEqual(world._cast_off_minor_faces(conn, {"off": ["G", "A"]}), ["Reinald"])
            where = dict(conn.execute("SELECT code, location_id FROM npcs WHERE code IN ('G', 'A')").fetchall())
        self.assertEqual(where, {"G": 1, "A": 2})


if __name__ == "__main__":
    unittest.main()
