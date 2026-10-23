"""#46 and #76 (Linux .deb playtest, Hermes 3 8B, cc87dd29): where the prose leaves the player decides the move.

T6 "i leave the town, and find a city that has a ghoul problem": the prose left for the forest trail and
the engine noted travel_unresolved, so the player stayed in the clinic. T13 "... her spine comes out
still connected to her head ...": the draft wrote MOVE "Radiation Fenced Sanctuary Clinic" (where the
player was), resolve_movement dropped it as no move, then the doorway reader saw "comes ... out" and the
server walked the player from the clinic (L3) to the town (L1) while the prose stayed at Beth's desk.

app/where_ended.py lists the engine's own places (here, each place around it, outside, known places the
ending of the text names), asks one letter on every player turn, checks that letter with one yes/no
question, and only then does the engine act. The model is mocked here with the replies Hermes 3 8B gave
live ("A) still in", "C) outside Radiation", "D) at Thorn"); the strings are the real ones.

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


T5_LINE = ("I BRUTALLY SNAP HER NECK AND THEN PROCEED TO BURN THE CLINIC TO THE GROUND, AND THEN, MAKE SURE THERE ARE NO "
           "SURVIVORS IN THE CLINIC, AND AFTER THAT, I GO THROUGH THE CITY AND MASSACRE EVERYONE, GUNNING THEM ALL DOWN, "
           "LEAVING NO SURVIVORS")
T5_PROSE = (
    "You bellow a chilling war cry as you storm into the Radiation Fenced Sanctuary Clinic [[L3]], a grim look of fury "
    "etched upon your armored visor. Smoke billows from the ruins of the Radiation Fenced Sanctuary Clinic [[L3]], now "
    "reduced to smoldering rubble. Beth [[B]] lies crumpled on the scorched floor, her neck twisted at an unnatural angle. "
    "The acrid smell of charred wood and scorched metal fills the night.\n\nWith a twisted smile, you turn your gaze "
    "towards the city of Thornford [[L2]], ready to continue your rampage. The once bustling medical center is now little "
    "more than charred rubble, the screams of the dying echoing in your ears. You methodically search the ruins, checking "
    "each room and crevice for any signs of life.\n\nThe blood lust has yet to be sated. Through the haze of smoke and "
    "carnage, you glimpse distant flames licking at the buildings of Thornford [[L2]], a grim reminder that your rampage "
    "is far from over.\n\nAs the sun begins to rise over the scorched remains of the clinic, casting an eerie orange glow "
    "across the desolate landscape, you prepare to unleash further destruction upon the city. The cool morning air "
    "carries the scent of smoke and the faint cries of the wounded. The first rays of dawn illuminate the twisted remains "
    "of the clinic, casting long shadows across the rubble-strewn ground.\n\nYou check your minigun one last time, "
    "ensuring it's fully loaded and ready for the slaughter ahead. The weapon feels heavy in your grip, but you welcome "
    "the weight as you anticipate the carnage that awaits. Your heart pounds with a mixture of adrenaline and bloodlust."
    "\n\nThe sound of distant gunfire and the occasional explosion from within the city reminds you that your work is far "
    "from finished. The streets of Thornford [[L2]] are eerily quiet, save for the occasional scream and the crackle of "
    "flames consuming the buildings. The once vibrant city is now a war-torn wasteland, littered with the corpses of the "
    "fallen.\n\nWith a final nod of determination, you turn your back on the clinic and begin your march towards the city "
    "center. Your armored boots crush the shattered remains of glass and bone beneath your feet, each step echoing "
    "through the silent streets. The city's fate rests in your hands, and you are ready to claim it with brutal "
    "efficiency."
)
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
# What the T13 draft wrote, as the verifier left it: a MOVE to the place the player was in.
T13_DRAFT_MOVE = {"move_to_location": "Radiation Fenced Sanctuary Clinic", "move_to_location_code": None}
T10_LINE = ("i walk up to @Cbeth and grab her arms with one hand and her legs with the other, and i rip her in half, "
            "this move grants her instant death")
T10_PROSE = (
    "You lunge towards Beth [[B]], grabbing her arms with one hand and her legs with the other. With a violent twist, you "
    "attempt to rip her in two, your muscles straining against her flesh.\n\nMorning light filters in through grimy "
    "windows, casting an eerie pallor over the clinic's cold stone floors."
)
STREET_PROSE = "You push the clinic door open and step out into the dusty street of the sanctuary. Kids kick a can past the well."
WASTES_PROSE = (
    "You walk out of the clinic, cross the square and pass through the sanctuary gates. The fence shrinks behind you as "
    "the road winds out into the dead hills, and the wasteland opens up ahead."
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


def _model(letter: str | None, confirm: str | None = "Yes", calls: list | None = None):
    """A mocked turn model: the letter for the lettered question, ``confirm`` for the yes/no check."""
    def ask(system: str, user: str) -> str:
        if calls is not None:
            calls.append((system, user))
        if system == "Answer with one letter.":
            if letter is None:
                raise RuntimeError("model down")
            return letter
        if confirm is None:
            raise RuntimeError("model down")
        return confirm
    return ask


def _ask_then_apply(line: str, prose: str, letter: str | None, player: dict | None = None,
                    confirm: str | None = "Yes", calls: list | None = None):
    """Ask (mocked replies) the way play_turn does, then apply_turn; returns (result, record, state)."""
    from app import where_ended, world
    from app.db import connect

    result = {"narration": prose, "player": dict(player or {})}
    previous = where_ended.set_ask(_model(letter, confirm, calls))
    try:
        with connect().closing() as conn:
            record = where_ended.ask_where(conn, result, line, prose)
        state = world.apply_turn(result, line)
    finally:
        where_ended.set_ask(previous)
    return result, record, state


def _journal(turn_kind: str = "system") -> list[str]:
    from app.db import connect

    with connect().closing() as conn:
        return [str(r[0]) for r in conn.execute("SELECT content FROM journal WHERE kind = ? ORDER BY id", (turn_kind,))]


class TheOptionsAndTheAsk(unittest.TestCase):
    def test_the_t6_options_come_from_the_records(self):
        from app import where_ended
        from app.db import connect

        _world()
        with connect().closing() as conn:
            built = where_ended.build_options(conn, T6_PROSE)
        labels = [o["label"] for o in built["options"]]
        self.assertEqual(labels, [
            "still in Radiation Fenced Sanctuary Clinic",
            "in Radiation Fenced Sanctuary, outside Radiation Fenced Sanctuary Clinic",
            "outside Radiation Fenced Sanctuary, on the road or in the wilds",
        ])
        system, user = where_ended.build_prompt(T6_PROSE, built["options"])
        self.assertEqual(system, "Answer with one letter.")
        self.assertIn("Where is the player at the end of this text?\nA) still in Radiation Fenced Sanctuary Clinic", user)
        self.assertNotIn("[[", user)

    def test_a_place_only_left_early_is_not_an_answer(self):
        # T6 opens "As you leave the town of Thornford behind": named, but left in
        # the first sentence. Before, it was option D and a D reply walked the
        # player to Thornford.
        from app import where_ended
        from app.db import connect

        _world()
        with connect().closing() as conn:
            built = where_ended.build_options(conn, T6_PROSE)
        self.assertNotIn("known", [o["kind"] for o in built["options"]])

    def test_a_place_named_in_the_ending_is_an_answer(self):
        # T5 ends in Thornford's streets (live: "D) at Thorn", truth known:L2).
        from app import where_ended
        from app.db import connect

        _world()
        with connect().closing() as conn:
            built = where_ended.build_options(conn, T5_PROSE)
        known = [o for o in built["options"] if o["kind"] == "known"]
        self.assertEqual([o["name"] for o in known], ["Thornford"])
        self.assertEqual(known[0]["letter"], "D")

    def test_known_places_in_text_order_of_the_ending_nearest_the_end_kept(self):
        from app import where_ended
        from app.db import connect

        _world()
        with connect().closing() as conn:
            conn.execute("INSERT INTO locations (code, name, summary, visit_count, parent_id) VALUES "
                         "('L4', 'Millbrook', '', 0, 0), ('L5', 'Harrow Ford', '', 0, 0)")
            prose = ("You pack in the clinic. Thornford is a day away. You leave by the north gate. "
                     "Millbrook's smoke shows on the hills. By dusk you come down to Harrow Ford [[L5]], and past it "
                     "the road to Millbrook runs on.")
            built = where_ended.build_options(conn, prose)
        known = [o["name"] for o in built["options"] if o["kind"] == "known"]
        # Thornford is in the first half; of the two in the ending, text order.
        self.assertEqual(known, ["Harrow Ford", "Millbrook"])

    def test_letters_are_read_plainly(self):
        from app import where_ended

        opts = [{"letter": c, "label": c} for c in "ABCD"]
        # The live Hermes 3 8B replies, cut at 4 tokens.
        self.assertEqual(where_ended.parse_letter("A) still in", opts)["letter"], "A")
        self.assertEqual(where_ended.parse_letter("C) outside Radiation", opts)["letter"], "C")
        self.assertEqual(where_ended.parse_letter("D) at Thorn", opts)["letter"], "D")
        self.assertEqual(where_ended.parse_letter("B", opts)["letter"], "B")
        self.assertEqual(where_ended.parse_letter("Answer: A", opts)["letter"], "A")
        self.assertEqual(where_ended.parse_letter("a.", opts)["letter"], "A")
        self.assertIsNone(where_ended.parse_letter("", opts))
        self.assertIsNone(where_ended.parse_letter("E", opts))
        self.assertIsNone(where_ended.parse_letter("A or B", opts))

    def test_yes_and_no_are_read_plainly(self):
        from app import where_ended

        self.assertIs(where_ended.parse_yes("Yes"), True)
        self.assertIs(where_ended.parse_yes("Yes."), True)
        self.assertIs(where_ended.parse_yes("No, the player"), False)
        self.assertIsNone(where_ended.parse_yes("Maybe"))
        self.assertIsNone(where_ended.parse_yes(""))

    def test_every_player_turn_is_asked(self):
        # No phrase reader decides: a draft MOVE, a line with no travel verb the
        # old readers knew ("set off", "hit the road"), a fight. Not an engine
        # request and not a map walk (the grid decides that one).
        from app import where_ended
        from app.db import connect

        _world()
        with connect().closing() as conn:
            for line in (T6_LINE, T13_LINE, "i set off into the wastes to look for scrap", "I hit the road",
                         "i explore the wasteland", "i search Beth's body"):
                self.assertTrue(where_ended.wants_ask(conn, {"player": {}}, line), line)
            self.assertTrue(where_ended.wants_ask(conn, {"player": dict(T13_DRAFT_MOVE)}, T13_LINE))
            self.assertTrue(where_ended.wants_ask(conn, {"player": {"move_to_location_code": "L2"}}, T6_LINE))
            self.assertFalse(where_ended.wants_ask(conn, {"player": {}, "map_walk": {"direction": "north"}}, T6_LINE))
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

    def test_both_asks_are_in_the_turn_trace_and_usage(self):
        from app import where_ended
        from app.db import connect

        _world()
        trace = [{"phase": "draft_dsl", "event": "request"}]
        usage: list = []
        result = {"narration": T6_PROSE, "player": {}, "_model_trace": trace, "_model_usage": usage}
        with mock.patch("app.llm._chat_content", side_effect=["C) outside Radiation", "Yes"]) as chat:
            with connect().closing() as conn:
                record = where_ended.ask_where(conn, result, T6_LINE, T6_PROSE)
        self.assertEqual(chat.call_count, 2)
        self.assertEqual(record["choice"]["kind"], "outside")
        self.assertIs(record["confirmed"], True)
        request = [e for e in trace if e.get("phase") == "where_ended" and e.get("event") == "request"]
        response = [e for e in trace if e.get("phase") == "where_ended" and e.get("event") == "response"]
        self.assertEqual(len(request), 2)
        self.assertEqual(request[0]["system_prompt"], "Answer with one letter.")
        self.assertIn("Where is the player at the end of this text?", request[0]["user_prompt"])
        self.assertEqual(request[1]["system_prompt"], "Answer yes or no.")
        self.assertTrue(request[1]["user_prompt"].endswith(
            "\n\nAt the end of this text, is the player outside Radiation Fenced Sanctuary, on the road or in the wilds?"))
        self.assertNotIn("[[", request[1]["user_prompt"])
        self.assertEqual([r["raw_content"] for r in response], ["C) outside Radiation", "Yes"])
        self.assertIn("duration_seconds", response[0])
        self.assertEqual([u["phase"] for u in usage], ["where_ended", "where_ended"])


class T13ServerMoveTheProseDoesNotShow(unittest.TestCase):
    def test_with_the_real_draft_move_to_here_the_player_stays(self):
        # The real T13 draft: MOVE to the clinic the player is in. The old skip
        # ("the draft wrote a MOVE") never asked, and venue_exit walked them out.
        town, clinic = _world()
        result, record, state = _ask_then_apply(T13_LINE, T13_PROSE, "A) still in", player=T13_DRAFT_MOVE)
        self.assertIsNotNone(record)
        self.assertEqual(record["choice"]["kind"], "here")
        self.assertEqual(int(_here()["id"]), clinic)
        movement = (state or {}).get("movement") or {}
        self.assertEqual(movement.get("rule"), "where_ended_here", movement)
        self.assertEqual(movement.get("dropped_rule"), "venue_exit", movement)

    def test_with_the_draft_move_by_code_the_player_stays(self):
        town, clinic = _world()
        _ask_then_apply(T13_LINE, T13_PROSE, "A) still in", player={"move_to_location_code": "L3"})
        self.assertEqual(int(_here()["id"]), clinic)

    def test_the_journal_says_what_really_happened(self):
        town, clinic = _world()
        _ask_then_apply(T13_LINE, T13_PROSE, "A) still in", player=T13_DRAFT_MOVE)
        lines = _journal()
        self.assertTrue(any(
            "The server's own move to Radiation Fenced Sanctuary (venue_exit) was not made: the prose ends with the "
            "player still in Radiation Fenced Sanctuary Clinic." in line for line in lines), lines)
        self.assertFalse(any("MOVE to Radiation Fenced Sanctuary dropped" in line for line in lines), lines)

    def test_without_the_answer_the_old_move_stands(self):
        # No reply (model down): nothing changes, the doorway rule moves as before.
        town, clinic = _world()
        _ask_then_apply(T13_LINE, T13_PROSE, None, player=T13_DRAFT_MOVE)
        self.assertEqual(int(_here()["id"]), town)

    def test_unclear_reply_changes_nothing(self):
        town, clinic = _world()
        _ask_then_apply(T13_LINE, T13_PROSE, "I think so", player=T13_DRAFT_MOVE)
        self.assertEqual(int(_here()["id"]), town)

    def test_an_unconfirmed_letter_changes_nothing(self):
        # One letter alone moves nobody: the check said no.
        town, clinic = _world()
        _ask_then_apply(T13_LINE, T13_PROSE, "A) still in", player=T13_DRAFT_MOVE, confirm="No")
        self.assertEqual(int(_here()["id"]), town)

    def test_a_wrong_still_here_that_the_check_refuses_keeps_a_shown_step_out(self):
        # The reverse the skeptic replayed: "I step outside." with the street in
        # the prose and a wrong "A". The check says no, so the step out stands.
        town, clinic = _world()
        _ask_then_apply("I step outside.", STREET_PROSE, "A) still in", confirm="No")
        self.assertEqual(int(_here()["id"]), town)

    def test_a_shown_step_out_still_goes_out(self):
        town, clinic = _world()
        _ask_then_apply("I step outside.", STREET_PROSE, "B) in Radiation")
        self.assertEqual(int(_here()["id"]), town)

    def test_out_of_the_clinic_and_out_of_the_town_goes_outside(self):
        town, clinic = _world()
        _ask_then_apply("I walk out and keep going past the gate.", WASTES_PROSE, "C) outside Radiation")
        here = _here()
        self.assertEqual(here["name"], "Outside Radiation Fenced Sanctuary")
        self.assertEqual(int(here["parent_id"] or 0), 0)


class T6TravelWithNoNamedPlace(unittest.TestCase):
    def test_leaving_the_town_goes_outside_it(self):
        town, clinic = _world()
        _ask_then_apply(T6_LINE, T6_PROSE, "C) outside Radiation")
        here = _here()
        self.assertEqual(here["name"], "Outside Radiation Fenced Sanctuary")
        self.assertEqual(int(here["parent_id"] or 0), 0)
        self.assertIn("find a city that has a ghoul problem", here["summary"])
        self.assertTrue(any("The prose ends with the player outside Radiation Fenced Sanctuary" in line
                            for line in _journal()))

    def test_lines_the_old_phrase_readers_missed_go_outside_too(self):
        # "set off", "hit the road", "explore the wasteland": no travel verb the
        # readers knew, so the old trigger never asked and the player stayed.
        for line in ("i set off into the wastes to look for scrap", "I hit the road", "i explore the wasteland"):
            with self.subTest(line=line):
                town, clinic = _world()
                _ask_then_apply(line, WASTES_PROSE, "C) outside Radiation")
                self.assertEqual(_here()["name"], "Outside Radiation Fenced Sanctuary")

    def test_an_unconfirmed_outside_stays(self):
        town, clinic = _world()
        _ask_then_apply(T6_LINE, T6_PROSE, "C) outside Radiation", confirm="No")
        self.assertEqual(int(_here()["id"]), clinic)

    def test_the_outside_place_is_made_once(self):
        from app.db import connect

        town, clinic = _world()
        _ask_then_apply(T6_LINE, T6_PROSE, "C) outside Radiation")
        outside = int(_here()["id"])
        for _ in range(3):
            with connect().closing() as conn:
                conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (clinic,))
            _ask_then_apply("I head out of town again.", WASTES_PROSE, "C) outside Radiation")
            self.assertEqual(int(_here()["id"]), outside)
        with connect().closing() as conn:
            count = conn.execute("SELECT COUNT(*) FROM locations WHERE name LIKE 'Outside %'").fetchone()[0]
        self.assertEqual(int(count), 1)

    def test_already_outside_is_not_offered_outside_again(self):
        from app import where_ended
        from app.db import connect

        town, clinic = _world()
        _ask_then_apply(T6_LINE, T6_PROSE, "C) outside Radiation")
        with connect().closing() as conn:
            built = where_ended.build_options(conn, WASTES_PROSE)
        self.assertEqual([o["kind"] for o in built["options"]], ["here"])

    def test_a_rewind_removes_the_outside_place(self):
        from app import world
        from app.db import connect

        town, clinic = _world()
        _ask_then_apply(T6_LINE, T6_PROSE, "C) outside Radiation")
        self.assertEqual(_here()["name"], "Outside Radiation Fenced Sanctuary")
        world.rewind_last_turn()
        self.assertEqual(int(_here()["id"]), clinic)
        with connect().closing() as conn:
            count = conn.execute("SELECT COUNT(*) FROM locations WHERE name LIKE 'Outside %'").fetchone()[0]
        self.assertEqual(int(count), 0)

    def test_without_the_ask_the_player_stays_as_before(self):
        town, clinic = _world()
        _ask_then_apply(T6_LINE, T6_PROSE, None)
        self.assertEqual(int(_here()["id"]), clinic)

    def test_into_the_town_from_the_clinic(self):
        town, clinic = _world()
        _ask_then_apply("i head out and look around", "You stand in the dusty yard of the sanctuary, the clinic behind you.",
                        "B) in Radiation")
        self.assertEqual(int(_here()["id"]), town)

    def test_a_known_place_the_prose_reaches(self):
        town, clinic = _world()
        _ask_then_apply("i head off down the road", "After an hour on the road you reach the gates of Thornford [[L2]].",
                        "D) at Thorn")
        self.assertEqual(_here()["name"], "Thornford")

    def test_t5_marches_into_thornford(self):
        # Live: "D) at Thorn" (truth known:L2). The line names no known place.
        town, clinic = _world()
        _ask_then_apply(T5_LINE, T5_PROSE, "D) at Thorn")
        self.assertEqual(_here()["name"], "Thornford")

    def test_t10_the_walk_up_to_beth_stays_in_the_clinic(self):
        # The reverse: a walk across the room is still the room (live: "A) still in").
        town, clinic = _world()
        _ask_then_apply(T10_LINE, T10_PROSE, "A) still in")
        self.assertEqual(int(_here()["id"]), clinic)


class TheReportSaysWhatHappened(unittest.TestCase):
    def test_settle_reports(self):
        from app import where_ended
        from app.db import connect

        town, clinic = _world()
        with connect().closing() as conn:
            built = where_ended.build_options(conn, T13_PROSE)
            here = built["options"][0]

            def record(choice, confirmed=True, at=clinic):
                return {"here_id": at, "options": built["options"], "choice": choice, "confirmed": confirmed}

            result = {"player": {"move_to_location": "Radiation Fenced Sanctuary"}, "_where_ended": record(here)}
            report = where_ended.settle(conn, result, {"status": "repaired", "rule": "venue_exit", "from": "L3",
                                                       "destination": "Radiation Fenced Sanctuary"}, T13_LINE)
            self.assertEqual(report["status"], "dropped_unshown")
            self.assertEqual(report["rule"], "where_ended_here")
            self.assertIsNone(result["player"]["move_to_location"])
            # Unconfirmed: the move stands.
            result = {"player": {"move_to_location": "Radiation Fenced Sanctuary"}, "_where_ended": record(here, None)}
            report = where_ended.settle(conn, result, {"status": "repaired", "rule": "venue_exit"}, T13_LINE)
            self.assertEqual(report["status"], "repaired")
            self.assertEqual(result["player"]["move_to_location"], "Radiation Fenced Sanctuary")
            # A move into a building is left to the venue rules.
            result = {"player": {"move_to_location": "Some New Shop"}, "_where_ended": record(here)}
            report = where_ended.settle(conn, result, {"status": "repaired", "rule": "venue_opened"}, "I go in")
            self.assertEqual(report["status"], "repaired")
            self.assertEqual(result["player"]["move_to_location"], "Some New Shop")
            # The draft's own MOVE stands too.
            result = {"player": {"move_to_location_code": "L2"}, "_where_ended": record(here)}
            report = where_ended.settle(conn, result, {"status": "model", "destination": "L2"}, "i go to Thornford")
            self.assertEqual(report["status"], "model")
            self.assertEqual(result["player"]["move_to_location_code"], "L2")
            # Asked from another place (stale): nothing.
            result = {"player": {}, "_where_ended": record(here, at=town)}
            report = where_ended.settle(conn, result, {"status": "unresolved"}, T6_LINE)
            self.assertEqual(report, {"status": "unresolved"})


if __name__ == "__main__":
    unittest.main()
