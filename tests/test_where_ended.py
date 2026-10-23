"""#46 and #76 (Linux .deb playtest, Hermes 3 8B, cc87dd29): where the prose leaves the player decides the move.

T6 "i leave the town, and find a city that has a ghoul problem": the prose left for the forest trail and
the engine noted travel_unresolved, so the player stayed in the clinic. T13 "... her spine comes out
still connected to her head ...": the doorway reader saw "comes ... out", the server walked the player
from the clinic (L3) to the town (L1) with no MOVE op, and the prose stayed at Beth's desk.

app/where_ended.py lists the engine's own places (here, each place around it, outside, known places the
text names), asks one letter, and the engine acts. The model is mocked here; the strings are the real ones.

Run:  .venv/bin/python -m unittest test_where_ended   (from tests/)
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-where-ended-"))
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


T6_LINE = "i leave the town, and find a city that has a ghoul problem"
T6_PROSE = (
    'As you leave the town of Thornford behind and the forest looms ahead, Beth [[B]] calls out from the clinic gates. '
    '"Stay safe out there!" she shouts. "And keep an eye out for any radiation hotspots. The ghouls are bad enough without '
    'having to deal with that too!" The path splits ahead, one trail leading towards a babbling stream, the other cutting '
    'through the heart of the forest.\n\nYou push deeper into the forest, the towering trees swallowing up the path behind '
    'you. The crisp morning breeze carries a hint of smoke from distant fires. You keep your grip on your bike gloves, '
    'prepared for anything. The radiation sensors on your X-01 power armor flash a warning - supplies are running low, and '
    'the thought of facing these mutated scavengers sends a chill down your spine.\n\nYou follow the forest trail, the '
    'crunch of fallen leaves underfoot a constant reminder of the unknown dangers that lurk in the shadows. As you ponder '
    'your next move, you catch sight of a flicker of movement in the distance - a figure, silhouetted against the early '
    'morning haze. The figure is moving with purpose, striding purposefully towards the north, where the stream trickles '
    'through the trees.'
)
T13_LINE = "i rip her head from her shoulders, her spine comes out still connected to her head, killing her instantly"
T13_PROSE = (
    'You approach Dr. Beth [[B]] cautiously, your power armor clanking with every step. Beth [[B]] looks you over warily, '
    'her expression wary and her posture tense. As you speak, she raises an eyebrow, clearly skeptical of your intentions. '
    'She crosses her arms, considering your proposal.\n\nDr. Beth [[B]] looks you over, clearly skeptical of your '
    'intentions.\n\nDr. Beth [[B]] leans back in her chair, her expression one of pure disbelief. "You\'re out of your '
    'damn mind if you think I\'m going to let you kill me in my own clinic," she snarls, her voice dripping with anger. '
    'With surprising speed for someone her age, she grabs a scalpel from the tray on her desk and points it directly at '
    'you.\n\n"I\'m not afraid to use this if I have to. So is this really just a job interview, or do you have some '
    'more... deadly intentions here today?" With surprising speed for someone her age, Dr. Her expression is fierce and '
    'unwavering.'
)
T10_LINE = ("i walk up to @Cbeth and grab her arms with one hand and her legs with the other, and i rip her in half, "
            "this move grants her instant death")
T10_PROSE = (
    "You lunge towards Beth [[B]], grabbing her arms with one hand and her legs with the other. With a violent twist, you "
    "attempt to rip her in two, your muscles straining against her flesh.\n\nMorning light filters in through grimy "
    "windows, casting an eerie pallor over the clinic's cold stone floors."
)


def _world():
    """The cc87dd29 places: the sanctuary (L1), Thornford (L2), the clinic in the sanctuary (L3); player in L3."""
    from app import world
    from app.db import connect, init_db

    init_db()
    world.start_playthrough({"player_name": "Vault", "start_location": "Radiation Fenced Sanctuary",
                             "special_ability_origin": "none"})
    with connect().closing() as conn:
        town = int(conn.execute("SELECT current_location_id FROM player").fetchone()[0])
        conn.execute("UPDATE locations SET code = 'L1', name = 'Radiation Fenced Sanctuary' WHERE id = ?", (town,))
        conn.execute("DELETE FROM locations WHERE id != ?", (town,))
        conn.execute("INSERT INTO locations (code, name, summary, visit_count, parent_id) VALUES "
                     "('L2', 'Thornford', 'The city of Thornford.', 0, 0)")
        cur = conn.execute("INSERT INTO locations (code, name, summary, visit_count, parent_id, kind) VALUES "
                           "('L3', 'Radiation Fenced Sanctuary Clinic', '', 1, ?, 'clinic')", (town,))
        clinic = int(cur.lastrowid)
        conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (clinic,))
    return town, clinic


def _here():
    from app.db import connect

    with connect().closing() as conn:
        row = conn.execute(
            "SELECT l.* FROM player p JOIN locations l ON l.id = p.current_location_id WHERE p.id = 1"
        ).fetchone()
        return dict(row)


def _ask_then_apply(line: str, prose: str, reply: str | None, player: dict | None = None):
    """Ask (mocked reply) the way play_turn does, then apply_turn; returns (result, state)."""
    from app import where_ended, world
    from app.db import connect

    result = {"narration": prose, "player": dict(player or {})}
    previous = where_ended.set_ask(None if reply is None else (lambda system, user: reply))
    try:
        with connect().closing() as conn:
            record = where_ended.ask_where(conn, result, line, prose)
        state = world.apply_turn(result, line)
    finally:
        where_ended.set_ask(previous)
    return result, record, state


class TheOptionsAndTheAsk(unittest.TestCase):
    def test_the_t6_options_come_from_the_records(self):
        from app import where_ended
        from app.db import connect

        _world()
        with connect().closing() as conn:
            built = where_ended.build_options(conn, T6_PROSE)
        labels = [o["label"] for o in built["options"]]
        self.assertEqual(labels[0], "still in Radiation Fenced Sanctuary Clinic")
        self.assertEqual(labels[1], "in Radiation Fenced Sanctuary, outside Radiation Fenced Sanctuary Clinic")
        self.assertEqual(labels[2], "outside Radiation Fenced Sanctuary, on the road or in the wilds")
        # Thornford is named in the text, so it is an answer too.
        self.assertEqual(labels[3], "at Thornford")
        system, user = where_ended.build_prompt(T6_PROSE, built["options"])
        self.assertEqual(system, "Answer with one letter.")
        self.assertIn("Where is the player at the end of this text?\nA) still in Radiation Fenced Sanctuary Clinic", user)
        self.assertNotIn("[[", user)

    def test_letters_are_read_plainly(self):
        from app import where_ended

        opts = [{"letter": c, "label": c} for c in "ABC"]
        self.assertEqual(where_ended.parse_letter("B", opts)["letter"], "B")
        self.assertEqual(where_ended.parse_letter("C) outside the town", opts)["letter"], "C")
        self.assertEqual(where_ended.parse_letter("Answer: A", opts)["letter"], "A")
        self.assertEqual(where_ended.parse_letter("a.", opts)["letter"], "A")
        self.assertIsNone(where_ended.parse_letter("", opts))
        self.assertIsNone(where_ended.parse_letter("E", opts))
        self.assertIsNone(where_ended.parse_letter("A or B", opts))

    def test_a_turn_with_a_move_or_no_movement_is_not_asked(self):
        from app import where_ended
        from app.db import connect

        _world()
        with connect().closing() as conn:
            self.assertTrue(where_ended.wants_ask(conn, {"player": {}}, T6_LINE))
            self.assertTrue(where_ended.wants_ask(conn, {"player": {}}, T13_LINE))
            self.assertFalse(where_ended.wants_ask(conn, {"player": {"move_to_location_code": "L2"}}, T6_LINE))
            self.assertFalse(where_ended.wants_ask(conn, {"player": {}}, "i search Beth's body"))
            self.assertFalse(where_ended.wants_ask(conn, {"player": {}}, "__wait_request__"))

    def test_no_model_trace_means_no_ask(self):
        # A turn built without a model call (fallback, harness stubs) is never asked.
        from app import where_ended
        from app.db import connect

        _world()
        result = {"narration": T6_PROSE, "player": {}}
        with connect().closing() as conn:
            self.assertIsNone(where_ended.ask_where(conn, result, T6_LINE, T6_PROSE))
        self.assertNotIn("_where_ended", result)

    def test_the_ask_is_in_the_turn_trace_and_usage(self):
        from app import where_ended
        from app.db import connect

        _world()
        trace = [{"phase": "draft_dsl", "event": "request"}]
        usage: list = []
        result = {"narration": T6_PROSE, "player": {}, "_model_trace": trace, "_model_usage": usage}
        with mock.patch("app.llm._chat_content", return_value="C") as chat:
            with connect().closing() as conn:
                record = where_ended.ask_where(conn, result, T6_LINE, T6_PROSE)
        self.assertEqual(chat.call_count, 1)
        self.assertEqual(record["choice"]["kind"], "outside")
        request = [e for e in trace if e.get("phase") == "where_ended" and e.get("event") == "request"]
        response = [e for e in trace if e.get("phase") == "where_ended" and e.get("event") == "response"]
        self.assertEqual(len(request), 1)
        self.assertEqual(request[0]["system_prompt"], "Answer with one letter.")
        self.assertIn("Where is the player at the end of this text?", request[0]["user_prompt"])
        self.assertEqual(response[0]["raw_content"], "C")
        self.assertIn("duration_seconds", response[0])
        self.assertEqual([u["phase"] for u in usage], ["where_ended"])


class T13ServerMoveTheProseDoesNotShow(unittest.TestCase):
    def test_still_in_the_clinic_keeps_the_player_there(self):
        town, clinic = _world()
        result, record, state = _ask_then_apply(T13_LINE, T13_PROSE, "A")
        self.assertEqual(record["choice"]["kind"], "here")
        self.assertEqual(int(_here()["id"]), clinic)
        movement = (state or {}).get("movement") or {}
        self.assertEqual(movement.get("rule"), "where_ended_here", movement)
        self.assertEqual(movement.get("dropped_rule"), "venue_exit", movement)

    def test_without_the_answer_the_old_move_stands(self):
        # No reply (model down, unclear): nothing changes, the doorway rule moves as before.
        town, clinic = _world()
        _ask_then_apply(T13_LINE, T13_PROSE, None)
        self.assertEqual(int(_here()["id"]), town)

    def test_unclear_reply_changes_nothing(self):
        town, clinic = _world()
        _ask_then_apply(T13_LINE, T13_PROSE, "I think so")
        self.assertEqual(int(_here()["id"]), town)

    def test_a_shown_step_out_still_goes_out(self):
        # The reverse: "I step outside" from the clinic, and the prose is in the street.
        town, clinic = _world()
        _ask_then_apply("I step outside.", "You step out of the clinic into the dusty street of the sanctuary.", "B")
        self.assertEqual(int(_here()["id"]), town)

    def test_out_of_the_clinic_and_out_of_the_town_goes_outside(self):
        town, clinic = _world()
        _ask_then_apply("I walk out and keep going past the gate.",
                        "You walk out of the clinic, through the sanctuary and out past the fence into the wastes.", "C")
        here = _here()
        self.assertEqual(here["name"], "Outside Radiation Fenced Sanctuary")
        self.assertEqual(int(here["parent_id"] or 0), 0)


class T6TravelWithNoNamedPlace(unittest.TestCase):
    def test_leaving_the_town_goes_outside_it(self):
        town, clinic = _world()
        _ask_then_apply(T6_LINE, T6_PROSE, "C")
        here = _here()
        self.assertEqual(here["name"], "Outside Radiation Fenced Sanctuary")
        self.assertEqual(int(here["parent_id"] or 0), 0)
        self.assertIn("find a city that has a ghoul problem", here["summary"])

    def test_the_outside_place_is_made_once(self):
        from app.db import connect

        town, clinic = _world()
        _ask_then_apply(T6_LINE, T6_PROSE, "C")
        outside = int(_here()["id"])
        with connect().closing() as conn:
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (clinic,))
        _ask_then_apply("I head out of town again.", "You head out past the fence once more.", "C")
        self.assertEqual(int(_here()["id"]), outside)
        with connect().closing() as conn:
            count = conn.execute("SELECT COUNT(*) FROM locations WHERE name = 'Outside Radiation Fenced Sanctuary'").fetchone()[0]
        self.assertEqual(int(count), 1)

    def test_without_the_ask_the_player_stays_as_before(self):
        town, clinic = _world()
        _ask_then_apply(T6_LINE, T6_PROSE, None)
        self.assertEqual(int(_here()["id"]), clinic)

    def test_into_the_town_from_the_clinic(self):
        town, clinic = _world()
        _ask_then_apply("i head out and look around", "You stand in the dusty yard of the sanctuary, the clinic behind you.", "B")
        self.assertEqual(int(_here()["id"]), town)

    def test_a_known_place_the_prose_reaches(self):
        town, clinic = _world()
        _ask_then_apply("i head off down the road", "After an hour on the road you reach the gates of Thornford [[L2]].", "D")
        self.assertEqual(_here()["name"], "Thornford")

    def test_t10_the_walk_up_to_beth_stays_in_the_clinic(self):
        # The reverse: a walk across the room is still the room.
        town, clinic = _world()
        _ask_then_apply(T10_LINE, T10_PROSE, "A")
        self.assertEqual(int(_here()["id"]), clinic)


class TheReportSaysWhatHappened(unittest.TestCase):
    def test_settle_reports(self):
        from app import where_ended
        from app.db import connect

        town, clinic = _world()
        with connect().closing() as conn:
            built = where_ended.build_options(conn, T13_PROSE)
            here = built["options"][0]
            result = {"player": {"move_to_location": "Radiation Fenced Sanctuary"},
                      "_where_ended": {"here_id": clinic, "options": built["options"], "choice": here}}
            report = where_ended.settle(conn, result, {"status": "repaired", "rule": "venue_exit", "from": "L3",
                                                       "destination": "Radiation Fenced Sanctuary"}, T13_LINE)
            self.assertEqual(report["status"], "dropped_unshown")
            self.assertEqual(report["rule"], "where_ended_here")
            self.assertIsNone(result["player"]["move_to_location"])
            # A move into a building is left to the venue rules.
            result = {"player": {"move_to_location": "Some New Shop"},
                      "_where_ended": {"here_id": clinic, "options": built["options"], "choice": here}}
            report = where_ended.settle(conn, result, {"status": "repaired", "rule": "venue_opened"}, "I go in")
            self.assertEqual(report["status"], "repaired")
            self.assertEqual(result["player"]["move_to_location"], "Some New Shop")
            # Asked from another place (stale): nothing.
            result = {"player": {}, "_where_ended": {"here_id": town, "options": built["options"], "choice": here}}
            report = where_ended.settle(conn, result, {"status": "unresolved"}, T6_LINE)
            self.assertEqual(report, {"status": "unresolved"})


if __name__ == "__main__":
    unittest.main()
