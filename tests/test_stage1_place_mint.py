"""Stage1 (Hermes 3 8B, 2026-10-25): places minted from text that is not a place.

T4: "I walk back to Dale, tell him the trough is patched, and ask him for my
five silver." Dale is the swineherd (the kind ask settled "Dale" as a person,
the prose files him as npc C). The venue rule made a place "The Dale", moved the
player into it over a confirmed where_ended "still in Back Stable Yard", while
the prose stayed in the stable yard.

T6: "I crouch among the reeds and search the mud for tracks, listening for the
beast." The draft's LOC_NEW "The marshes." (full stop and all) was filed as a
new place at The Shore; the player did not move.

T5: "I head out to the shore of the flats ..." still makes The Shore.

Run:  .venv/bin/python -m unittest tests.test_stage1_place_mint
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-stage1-place-"))
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


T4_LINE = "I walk back to Dale, tell him the trough is patched, and ask him for my five silver."
T4_PROSE = (
    "You walk back to Dale [[C]], the swineherd, in the cool morning air. The stable yard is quiet now, with only a few "
    "horses still munching hay in their stalls. You find Dale [[C]] near the trough you patched yesterday.\n\n"
    "\"Ah, you're back,\" Dale [[C]] says with a nod. \"The trough is patched well. You've done good work there.\""
)
T5_LINE = "I head out to the shore of the flats to look for whatever beast has been prowling the marsh."
T5_PROSE = (
    "The marshy flats stretch out before you, a vast expanse of reeds, pools and the occasional clump of trees. A light "
    "breeze rustles the grasses. You can hear the distant call of birds and the lowing of cattle from the farmsteads "
    "dotting the landscape.\n\nA path of hardened earth cuts through the marsh, leading to the distant shore. You follow "
    "it, boots squelching in the damp soil. The sun is just rising, casting a golden glow over the scene.\n\nAs you walk, "
    "you scan the tall grasses, alert for any sign of the beast."
)
T6_LINE = "I crouch among the reeds and search the mud for tracks, listening for the beast."
T6_PROSE = (
    "The sun is rising over the marshes, casting a warm glow on the tall reeds that surround you. You crouch low, eyes "
    "closed, focusing intently on the task at hand - searching the mud for tracks. The gentle wind rustles through the "
    "grasses, creating a soothing symphony of natural sounds. In the distance, the distant sound of a boat on the river "
    "drifts through the air, a reminder of the world beyond these marshes. As you concentrate on your task, the cool mud "
    "squelches between your fingers as you probe the earth for any sign of the beast that has been eluding you. The reeds "
    "sway gently in the breeze, providing a natural barrier between you and whatever dangers may lurk in the marshes. The "
    "sound of the boat grows fainter, and for a moment, you are completely alone, lost in thought and the task at hand."
)


def _world(here: str = "Back Stable Yard", kind: str = "stable") -> int:
    """Saltmarrow (L1) with the player in a child place; Mattias and Man 1 on the roster (as at T4)."""
    from app import world
    from app.db import connect, init_db

    init_db()
    world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
    with connect().closing() as conn:
        town = int(conn.execute("SELECT id FROM locations WHERE name = 'Saltmarrow'").fetchone()[0])
        cur = conn.execute(
            "INSERT INTO locations (code, name, summary, visit_count, parent_id, kind) VALUES (?, ?, '', 1, ?, ?)",
            (world._next_code(conn, "locations", "L"), here, town, kind),
        )
        place = int(cur.lastrowid)
        conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (place,))
        for code, name, role in (("A", "Mattias", "toll keeper"), ("B", "Man 1", "rag picker")):
            conn.execute("INSERT INTO npcs (code, location_id, name, role) VALUES (?, ?, ?, ?)",
                         (code, place, name, role))
        conn.commit()
    return place


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
        return str(conn.execute(
            "SELECT l.name FROM player p JOIN locations l ON l.id = p.current_location_id WHERE p.id = 1").fetchone()[0])


def _place_names() -> list[str]:
    from app.db import connect

    with connect().closing() as conn:
        return [str(r[0]) for r in conn.execute("SELECT name FROM locations ORDER BY id").fetchall()]


def _apply(result: dict, line: str, letter: str | None = None, confirm: str = "Yes") -> None:
    from app import where_ended, world
    from app.db import connect

    previous = where_ended.set_ask((lambda s, u: letter if s == "Answer with one letter." else confirm)
                                   if letter else None)
    try:
        if letter:
            with connect().closing() as conn:
                where_ended.ask_where(conn, result, line, result["narration"])
        world.apply_turn(result, line)
    finally:
        where_ended.set_ask(previous)


class AWalkToAPersonMakesNoPlace(unittest.TestCase):
    def _t4_result(self) -> dict:
        return {
            "narration": T4_PROSE,
            "player": {},
            "npcs": [{"code": "C", "name": "Dale", "role": "swineherd", "summary": "", "attitude": "neutral",
                      "location": "", "presence": "event_worthy", "shell": False, "power_rank": 8,
                      "_seeded_from_narration": True}],
            "_entity_kinds": {"dale": "person"},
        }

    def test_t4_dale_settled_as_a_person_is_no_place(self):

        _world()
        with _notes() as ledger:
            _apply(self._t4_result(), T4_LINE, "A) still in", "Yes")
        self.assertNotIn("The Dale", _place_names())
        self.assertEqual(_here(), "Back Stable Yard")
        decisions = [n.get("decision") for n in ledger.notes]
        self.assertIn("destination_is_a_person", decisions)

    def test_t4_dale_on_the_roster_is_no_place(self):
        from app import world
        from app.db import connect

        place = _world()
        with connect().closing() as conn:
            conn.execute("INSERT INTO npcs (code, location_id, name, role) VALUES ('C', ?, 'Dale', 'swineherd')", (place,))
            here = str(conn.execute("SELECT code FROM locations WHERE id = ?", (place,)).fetchone()[0])
            self.assertEqual(world._venue_requested_and_reached(conn, T4_LINE, T4_PROSE, here), "")
            conn.rollback()

    def test_a_confirmed_still_here_holds_a_venue_request(self):
        # The class, apart from Dale: a place the line asks for and the venue rule makes does
        # not move the player over a checked "still in <here>".
        from app import where_ended
        from app.db import connect

        place = _world()
        result = {"narration": T4_PROSE, "player": {"move_to_location": "The Dale"}}
        with connect().closing() as conn:
            conn.execute("INSERT INTO locations (code, name, summary, visit_count, parent_id) "
                         "VALUES ('L9', 'The Dale', '', 0, (SELECT parent_id FROM locations WHERE id = ?))", (place,))
            conn.commit()
            previous = where_ended.set_ask(lambda s, u: "A) still in" if s == "Answer with one letter." else "Yes")
            try:
                where_ended.ask_where(conn, result, T4_LINE, T4_PROSE)
            finally:
                where_ended.set_ask(previous)
            report = {"status": "repaired", "rule": "venue_requested", "from": "L2", "destination": "The Dale"}
            with _notes() as ledger:
                out = where_ended.settle(conn, result, report, T4_LINE)
        self.assertEqual(out["status"], "dropped_unshown")
        self.assertEqual(out["held_offer"], "The Dale")
        self.assertIsNone(result["player"]["move_to_location"])
        self.assertIn("move_held_where_ended_confirmed", [n.get("decision") for n in ledger.notes])


class APlaceNameIsMatchedBeforeItIsMinted(unittest.TestCase):
    def test_t6_the_marshes_with_no_marsh_on_record_is_the_ground_here(self):

        _world("The Shore", "")
        before = _place_names()
        result = {"narration": T6_PROSE, "player": {},
                  "locations": [{"name": "The marshes.", "summary": "Discovered location: The marshes."}]}
        with _notes() as ledger:
            _apply(result, T6_LINE)
        self.assertEqual(_place_names(), before)
        self.assertEqual(_here(), "The Shore")
        ground = [n for n in ledger.notes if n.get("decision") == "place_is_the_ground_here"]
        self.assertEqual(len(ground), 1)
        self.assertEqual(ground[0]["name"], "The marshes")
        self.assertEqual(ground[0]["here"], "The Shore")

    def test_a_lower_case_place_that_is_not_ground_still_files(self):
        # The same turn shape with a building named in passing: "the old mill" is a place to go later.
        _world("The Shore", "")
        prose = T6_PROSE + " Beyond the reeds you glimpse the old mill, its wheel long still."
        result = {"narration": prose, "player": {}, "locations": [{"name": "the old mill", "summary": ""}]}
        with _notes() as ledger:
            _apply(result, T6_LINE)
        self.assertIn("the old mill", [n.lower() for n in _place_names()])
        self.assertEqual(_here(), "The Shore")
        self.assertNotIn("place_is_the_ground_here", [n.get("decision") for n in ledger.notes])

    def test_t6_the_marshes_beside_a_marsh_on_record_is_that_marsh(self):
        from app import world
        from app.db import connect

        _world("The Shore", "")
        with connect().closing() as conn:
            conn.execute("INSERT INTO locations (code, name, summary, visit_count, parent_id) VALUES "
                         "(?, 'The Deep Marsh', '', 0, (SELECT parent_id FROM locations WHERE name = 'The Shore'))",
                         (world._next_code(conn, "locations", "L"),))
            conn.commit()
        before = _place_names()
        result = {"narration": T6_PROSE.replace("the marshes", "the Marshes"), "player": {},
                  "locations": [{"name": "The Marshes.", "summary": ""}]}
        with _notes() as ledger:
            _apply(result, T6_LINE)
        self.assertEqual(_place_names(), before)
        self.assertIn("place_matched_existing", [n.get("decision") for n in ledger.notes])

    def test_a_named_place_loses_its_full_stop(self):
        from app import world

        self.assertEqual(world._clean_place_name("The marshes."), "The marshes")
        self.assertEqual(world._clean_place_name(" \"Gull Rock\"! "), "Gull Rock")
        self.assertEqual(world._singular_word("marshes"), "marsh")
        self.assertEqual(world._singular_word("pass"), "pass")


class TheShoreStillComes(unittest.TestCase):
    def test_t5_the_shore_of_the_flats_makes_the_shore(self):
        _world()
        result = {"narration": T5_PROSE, "player": {}}
        _apply(result, T5_LINE)
        self.assertIn("The Shore", _place_names())
        self.assertEqual(_here(), "The Shore")


if __name__ == "__main__":
    unittest.main()
