"""cheat100 (Hermes 3 8B, a Sonnet player, 2026-10-25): travel by the player's own place code.

The codes in the player's line (#L5, like @A and !I1) are references the
engine binds. A place the line goes to by its code is the player's own ask,
the strongest signal a turn has, and it lost to everything else:

T63: "I walk to #L5 Dunstan's General Store and ask @I what he would pay for a
plain wool tunic." (at Outside Saltmarrow). The line names the store outright,
so the reference was never bound; the draft wrote MOVE "Bartholomew's Inn" with
a LOC for it, the new_location rule took the inn over the player's place, and
the venue gate stood the player in Saltmarrow.

T33 "I walk to #L5 to look for the baker's boy." and T34 "I step inside #L5 and
ask @I ...": bound (place_bound_by_reference L5), then dropped by a "still in
Saltmarrow" where-ended answer (server_move_not_shown, rule player_input).

T76 "#L1" (in the inn): a line that is only a code. The going ask was shown
"Saltmarrow" alone and said no; nothing moved. T85 "#L5": bound, then read as
no travel (intent general) and nothing moved. T77 "I put on my coat, leave the
inn and walk out into the street of #L1 to look for work." worked.

T83 "I leave the inn and walk to #L5, Dunstan's General Store." The draft's
MOVE was L5 itself (not another place): the save went Bartholomew's Inn ->
Outside Capital City (L4) because the store's record has stood in Outside
Capital City since T16 ("Outside the city ... You spot a chandler's shop to the
left, Dunstan's General Store") and the venue gate ends a journey to a shop
across the map at the place it stands in. The prose kept the player outside the
inn in Saltmarrow (where_ended "in Saltmarrow, outside Bartholomew's Inn").
That landing is the gate on the store's record, not the draft; it stays.

Now: a #L code the line types that resolves to a roster place is the turn's
destination (rule player_code), before and over the draft's MOVE, a place the
draft minted and the where-ended answer; a bare code line is "I go there";
an unknown code (#L99) binds nothing and the draft's invented place does not
take its place.

Run:  .venv/bin/python -m unittest tests.test_cheat100_code_travel
"""
from __future__ import annotations

import contextlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-cheat100-codetravel-"))
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


T63_LINE = "I walk to #L5 Dunstan's General Store and ask @I what he would pay for a plain wool tunic."
T63_PROSE = (
    "You approach the front of Dunstan's General Store [[L5]], a single-story building with a worn wooden sign hanging "
    "out front. The door is open, revealing a small shop interior. You step inside the cool shadows of the store.\n\n"
    "\"Hello there,\" calls out the voice of Dunstan [[I]] from the back. \"Looking for something in particular?\"\n\n"
    "You clear your throat and ask, \"I'm interested in a plain wool tunic. What would you pay for one?\""
)
T76_LINE = "#L1"
T76_PROSE = (
    "You sit at a table in the common room of Bartholomew's Inn [[L2]], a modest establishment in the center of "
    "Saltmarrow [[L1]]. A fire crackles in the hearth, and the scent of roasting meat and ale mingles in the warm fug."
)
T77_LINE = "I put on my coat, leave the inn and walk out into the street of #L1 to look for work."
T77_PROSE = (
    "You step out of Bartholomew's Inn [[L2]] into the chill evening air. Saltmarrow [[L1]]'s streets are quiet, the "
    "flickering light of oil lamps casting long pools on the cobblestones. You pull your coat close and start walking, "
    "eyes scanning the faces of the folk you pass."
)
T83_LINE = "I leave the inn and walk to #L5, Dunstan's General Store."
T83_PROSE = (
    "You step out of Bartholomew's Inn [[L2]] into the cool salt air of evening, the door swinging shut behind you. The "
    "cobbled street is quiet but for the occasional laughter from the inn. To the north, the road leads to the harbour "
    "and the ruined docks of Saltmarrow [[L1]]. To the east, it winds toward the higher ground and the city walls. You "
    "pause for a moment, considering your next move, when a voice calls out from behind you."
)
T85_LINE = "#L5"
T85_PROSE = (
    "Evening falls, the golden hour fading to a cooler blue as the sun dips toward the horizon. The street is busy with "
    "people hurrying home from their day's labors. As you walk, you notice the door to the store swings open again."
)


def _world(store_in: str = "Saltmarrow", here: str = "Bartholomew's Inn", minute: int = 600) -> dict[str, int]:
    """The cheat100 roster: L1 Saltmarrow, L2 the inn in it, L3 Capital City, L4 Outside Capital City, L5 Dunstan's
    General Store (filed in ``store_in``), L6 City Gate, L7 Outside Saltmarrow; player at ``here``; the clock at ``minute``."""
    from app import world
    from app.db import connect, init_db

    init_db()
    world.start_playthrough({"player_name": "Isk Tarrow", "start_location": "Saltmarrow", "special_ability_origin": "none"})
    with connect().closing() as conn:
        town = int(conn.execute("SELECT id FROM locations WHERE name = 'Saltmarrow'").fetchone()[0])
        conn.execute("UPDATE locations SET code = 'L1' WHERE id = ?", (town,))
        conn.execute("DELETE FROM locations WHERE id != ?", (town,))
        ids = {"Saltmarrow": town}
        for code, name, parent, kind in (
            ("L2", "Bartholomew's Inn", "Saltmarrow", "inn"),
            ("L3", "Capital City", "", ""),
            ("L4", "Outside Capital City", "", ""),
            ("L5", "Dunstan's General Store", store_in, "general_store"),
            ("L6", "City Gate", "", ""),
            ("L7", "Outside Saltmarrow", "", ""),
        ):
            cur = conn.execute(
                "INSERT INTO locations (code, name, summary, visit_count, parent_id, kind) VALUES (?, ?, '', 1, ?, ?)",
                (code, name, ids.get(parent, 0), kind),
            )
            ids[name] = int(cur.lastrowid)
        # The store's recorded hours, 07:00-19:00 ("closed now (07:00-19:00)", T86).
        conn.execute("UPDATE locations SET open_minute = 420, close_minute = 1140 WHERE code = 'L5'")
        conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (ids[here],))
        conn.execute("INSERT INTO npcs (code, location_id, name, role) VALUES ('A', ?, 'Bartholomew', 'innkeeper')",
                     (ids["Bartholomew's Inn"],))
        conn.execute("INSERT INTO npcs (code, location_id, name, role) VALUES ('I', ?, 'Dunstan', 'storekeeper')",
                     (ids["Dunstan's General Store"],))
        world._pacing_set(conn, "world_minute", minute)
        conn.commit()
    return ids


@contextlib.contextmanager
def _notes():
    from app import turn_ledger

    ledger = turn_ledger.Ledger("test")
    token = turn_ledger._CURRENT.set(ledger)
    try:
        yield ledger
    finally:
        turn_ledger._CURRENT.reset(token)


def _here() -> str:
    from app.db import connect

    with connect().closing() as conn:
        return str(conn.execute("SELECT l.name FROM player p JOIN locations l ON l.id = p.current_location_id "
                                "WHERE p.id = 1").fetchone()[0])


def _place_names() -> list[str]:
    from app.db import connect

    with connect().closing() as conn:
        return [str(r[0]) for r in conn.execute("SELECT name FROM locations ORDER BY id").fetchall()]


def _turn(result: dict, line: str, *, going: str = "Yes", letter: str | None = None, confirm: str = "No."):
    """The real order of play_turn: the reference asks, the where-ended ask, then apply_turn. Returns the report."""
    from app import entity_kinds, where_ended, world
    from app.db import connect

    asks: list[str] = []

    def kind_ask(system, user, *, trace=None, usage=None, phase="", max_tokens=0):
        asks.append(user)
        return going

    prev_kind = entity_kinds.set_kind_ask(kind_ask)
    prev_where = where_ended.set_ask((lambda s, u: letter if s == "Answer with one letter." else confirm)
                                     if letter else None)
    try:
        entity_kinds.settle_place_reference(result, line)
        if letter:
            with connect().closing() as conn:
                where_ended.ask_where(conn, result, line, result["narration"])
        state = world.apply_turn(result, line)
    finally:
        entity_kinds.set_kind_ask(prev_kind)
        where_ended.set_ask(prev_where)
    result["_asks"] = asks
    return (state or {}).get("movement") or {}


def _decisions(ledger, name: str) -> list[dict]:
    return [n for n in ledger.notes if n.get("decision") == name]


class ThePlayersCodeIsTheDestination(unittest.TestCase):
    def test_t83_the_code_beats_the_drafts_move_and_the_where_ended_answer(self):
        # The store where the later scenes put it (in Saltmarrow) and a draft MOVE to another place:
        # the line's #L5 goes to L5 whatever the draft says; the recorded where-ended answers
        # ("B) in Salt", "No.") disagree and are only kept for measurement.
        _world()
        result = {"narration": T83_PROSE, "player": {"move_to_location_code": "L4", "move_to_location": None}}
        with _notes() as ledger:
            report = _turn(result, T83_LINE, letter="B) in Salt")
        self.assertEqual(_here(), "Dunstan's General Store")
        self.assertEqual(report.get("rule"), "player_code", report)
        travel = _decisions(ledger, "player_code_travel")
        self.assertTrue(travel, ledger.notes)
        self.assertEqual(travel[0]["code"], "L5")
        self.assertEqual(travel[0]["replaced"], "Outside Capital City")
        bound = _decisions(ledger, "place_bound_by_reference")
        self.assertEqual((bound[0]["code"], bound[0]["how"]), ("L5", "typed_and_named"))
        self.assertEqual(result["_asks"], [], "a code typed beside its own name needs no going ask")

    def test_t83_as_recorded_the_store_filed_outside_the_capital_is_reached_by_its_door_place(self):
        # The recorded save: L5 stands in Outside Capital City (since T16) and the draft's MOVE was L5.
        # The venue gate ends the journey at the place the store stands in; that is the record, not the draft.
        _world(store_in="Outside Capital City", minute=1165)
        result = {"narration": T83_PROSE, "player": {"move_to_location_code": "L5", "move_to_location": None}}
        with _notes():
            report = _turn(result, T83_LINE, letter="B) in Salt")
        self.assertEqual(_here(), "Outside Capital City")
        self.assertEqual(report.get("rule"), "player_code", report)
        self.assertIn("entered from Outside Capital City", str(report.get("reason") or ""))

    def test_t63_the_code_beats_the_place_the_draft_minted(self):
        # Recorded draft: MOVE "Bartholomew's Inn" and a LOC for it; the save went to Saltmarrow by the inn.
        _world(here="Outside Saltmarrow")
        result = {
            "narration": T63_PROSE,
            "player": {"move_to_location_code": None, "move_to_location": "Bartholomew's Inn"},
            "locations": [{"name": "Bartholomew's Inn",
                           "summary": "A small inn just outside of Saltmarrow, with a few stables out back."}],
        }
        with _notes() as ledger:
            report = _turn(result, T63_LINE)
        self.assertEqual(report.get("rule"), "player_code", report)
        self.assertEqual(_decisions(ledger, "player_code_travel")[0]["replaced"], "Bartholomew's Inn")
        # From outside the town the shop is entered from the town it stands in (the venue gate).
        self.assertEqual(_here(), "Saltmarrow")
        self.assertIn("entered from Saltmarrow", str(report.get("reason") or ""))
        # Standing in the town, the same line walks in.
        _world(here="Saltmarrow")
        result = {"narration": T63_PROSE, "player": {"move_to_location": "Bartholomew's Inn"},
                  "locations": [{"name": "Bartholomew's Inn", "summary": "A small inn."}]}
        _turn(result, T63_LINE)
        self.assertEqual(_here(), "Dunstan's General Store")

    def test_t33_a_still_here_answer_does_not_drop_the_code(self):
        # Recorded: bound L5 (going "Yes"), then "A) still in" / "Yes" held it (server_move_not_shown).
        _world(here="Saltmarrow")
        prose = ("You walk through the rubble-strewn streets of Saltmarrow [[L1]], heading towards the general store at "
                 "the end of the main road. The store is a simple wooden building, with a sign reading \"Dunstan's "
                 "General Store\" hanging crookedly above the door.")
        with _notes() as ledger:
            report = _turn({"narration": prose, "player": {}}, "I walk to #L5 to look for the baker's boy.",
                           letter="A) still in", confirm="Yes")
        self.assertEqual(_here(), "Dunstan's General Store")
        self.assertEqual(report.get("rule"), "player_code", report)
        self.assertFalse(_decisions(ledger, "server_move_not_shown"))

    def test_t77_a_code_inside_a_sentence_still_moves(self):
        _world()
        with _notes():
            report = _turn({"narration": T77_PROSE, "player": {}}, T77_LINE, letter="B) in Salt", confirm="Yes, the text")
        self.assertEqual(_here(), "Saltmarrow")
        self.assertEqual(report.get("rule"), "player_code", report)


class ABareCodeLineGoesThere(unittest.TestCase):
    def test_t76_bare_l1_leaves_the_inn_for_the_town(self):
        # Recorded: the going ask (shown "Saltmarrow") said "No. The player"; the save stayed in the inn.
        _world()
        result = {"narration": T76_PROSE, "player": {}}
        with _notes() as ledger:
            report = _turn(result, T76_LINE, going="No. The player", letter="A) still in", confirm="Yes, you are")
        self.assertEqual(_here(), "Saltmarrow")
        self.assertEqual(report.get("rule"), "player_code", report)
        self.assertEqual(result["_asks"], [], "a bare code is not asked")
        self.assertEqual(_decisions(ledger, "place_bound_by_reference")[0]["how"], "bare_code")

    def test_t85_bare_l5_enters_the_store_from_the_place_it_stands_in(self):
        # Recorded: bound L5, then not_travel (intent general); the save stayed Outside Capital City.
        _world(store_in="Outside Capital City", here="Outside Capital City")
        with _notes():
            report = _turn({"narration": T85_PROSE, "player": {}}, T85_LINE, letter="A) still in", confirm="Yes")
        self.assertEqual(_here(), "Dunstan's General Store")
        self.assertEqual(report.get("rule"), "player_code", report)

    def test_t85_as_recorded_the_store_is_closed_at_that_hour(self):
        # The recorded clock (world minute 1171 on day 4, 19:31) is past the store's 07:00-19:00:
        # the move is refused by the hours, as T86's door was.
        _world(store_in="Outside Capital City", here="Outside Capital City", minute=1171)
        with _notes():
            report = _turn({"narration": T85_PROSE, "player": {}}, T85_LINE, letter="A) still in", confirm="Yes")
        self.assertEqual(_here(), "Outside Capital City")
        self.assertEqual(report.get("refused"), "venue_closed", report)

    def test_the_shapes_of_a_bare_code_line(self):
        from app import entity_kinds
        from app.db import connect

        _world()
        with connect().closing() as conn:
            rows = conn.execute("SELECT id, code, name, parent_id, kind FROM locations ORDER BY id").fetchall()
        for line in ("#L1", " #l1. ", "[[L1]]", "#L1!"):
            found = entity_kinds._typed_code_travel(rows, line, "Bartholomew's Inn")
            self.assertIsNotNone(found, line)
            self.assertEqual((str(found[0]["code"]), found[1]), ("L1", "bare_code"), line)
        # The place the player is in, an unknown code, and a code in a sentence with no name: not bare.
        for line in ("#L2", "#L99", "I look at #L1"):
            self.assertIsNone(entity_kinds._typed_code_travel(rows, line, "Bartholomew's Inn"), line)
        # A named place whose code is typed only as where the player comes from, or a line with no travel.
        self.assertIsNone(entity_kinds._typed_code_travel(rows, "I leave #L5 and go to Saltmarrow", "Dunstan's General Store"))
        self.assertIsNone(entity_kinds._typed_code_travel(rows, "I ask Dunstan about #L1 Saltmarrow", "Bartholomew's Inn"))


class AnUnknownCodeBindsNothing(unittest.TestCase):
    def test_l99_moves_nowhere_and_the_drafts_invented_place_does_not_stand_in(self):
        _world()
        prose = ("You step out of Bartholomew's Inn [[L2]] and walk to the Sunken Market, where stalls lean against "
                 "the sea wall.")
        result = {"narration": prose, "player": {"move_to_location": "The Sunken Market"},
                  "locations": [{"name": "The Sunken Market", "summary": "Stalls against the sea wall."}]}
        with _notes() as ledger:
            report = _turn(result, "#L99", going="Yes")
        self.assertEqual(_here(), "Bartholomew's Inn")
        self.assertFalse(_decisions(ledger, "place_bound_by_reference"))
        self.assertEqual(report.get("rule"), "unknown_code", report)
        self.assertEqual(_decisions(ledger, "unknown_code_no_move")[0]["dropped"], "The Sunken Market")

    def test_a_declared_code_is_still_held(self):
        # "I am in #L5" states where the player is; the declared-move hold stays in charge.
        _world()
        with _notes() as ledger:
            _turn({"narration": T83_PROSE, "player": {"move_to_location_code": "L5"}},
                  "I am now in #L5, Dunstan's General Store.", going="Yes")
        self.assertEqual(_here(), "Bartholomew's Inn")
        self.assertTrue(_decisions(ledger, "move_held_declared"), ledger.notes)


if __name__ == "__main__":
    unittest.main()
