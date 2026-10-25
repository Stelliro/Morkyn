"""Stage2 (Hermes 3 8B, 2026-10-25): a new place named with its preposition, and a move the prose did not confirm.

T5: "I tell Reinald to come along anyway, and I walk out of town onto the mudflats
toward the marsh edge ..." The draft wrote ``MOVE to Marsh Edge``; the engine
filed a place called "to Marsh Edge" and, because the walk was on foot from inside
the town, adopted it as a part of Saltmarrow (new_place_in_town) although the line
walks out of town.

T10: "I lower my knife, tell Reinald to stay close, and follow the clawed prints
deeper into the reeds to find the beast itself." The prose's "The prints lead you
deeper into the heart of Saltmarrow" made the follow_named rule walk the player
back to the town (L1). where_ended answered "B) in Saltmarrow, outside to Marsh
Edge" but the check said "Yes, you are" (still in the marsh): not confirmed, and
the move stood. Reinald stayed at L2 and Wat Thatcher was filed at L1.

T6 and T7 (no move recorded) are kept as they were.

Run:  .venv/bin/python -m unittest tests.test_stage2_place_move
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-stage2-place-move-"))
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


T5_LINE = ("I tell Reinald to come along anyway, and I walk out of town onto the mudflats toward the marsh edge to look "
           "for whatever has been dragging bodies about.")
T5_PROSE = (
    "You step out of the Saltmarrow [[L1]] town gates with Reinald [[C]] in tow, the sun rising over the mudflats "
    "stretching out ahead of you. The marsh edge lies not far off, a dark blur on the horizon where the wetlands begin. "
    "You've no idea what might be responsible for the bodies, but someone has been dragging them this way, the trail of "
    "blood clearly visible. Reinald [[C]] seems hesitant to follow you out here."
)
T6_LINE = "I crouch and follow the blood trail toward the reeds, looking for the beast that made it."
T6_PROSE = (
    "You crouch and follow the blood trail toward the reeds, hoping to find the beast that made it. The trail leads into "
    "the marsh, and you pick your way carefully through the shallow water. The blood is fresh, and you can see the prints "
    "of clawed feet. The creature has left a clear trail into the heart of the marsh.\n\nYou push through the reeds and "
    "find a clearing. In the center, a hunched figure lies still on the ground. It's a man, his clothes tattered and "
    "bloody. You wade out to where he lies and kneel beside him. His face is pale and his breathing shallow.\n\nHe opens "
    "his eyes and blinks at you. \"The marsh... it took my crew. I barely escaped.\" His voice is weak. \"We were "
    "charting the new waters, but the tides... they rose too fast. My men... I barely made it back to the town. The reeve "
    "won't send help. Not here.\"\n\nYou listen to his story, and decide what to do. You can't leave him here alone. The "
    "marsh is too dangerous. But Saltmarrow [[L1]] is too far. There's a shelter not far from here, a place to rest and "
    "think. You'll take him there first, then decide what to do.\n\n\"Come on. I'll take you somewhere safe. We can "
    "figure this out later.\""
)
T7_LINE = ("I ask the injured man what took his crew and which way it went, and I tell Reinald to keep watch behind me.")
T7_PROSE = (
    "You stand with Reinald [[C]] in the grey light of early dawn on the edge of the flooded district of Saltmarrow. "
    "Patches of mist swirl over the muddy water and the shadows of half-submerged buildings.\n\n\"Keep watch behind me,\" "
    "you tell Reinald [[C]] as you turn to the injured man lying on a pallet nearby. \"What took your crew and which way "
    "it went?\"\n\nThe man's face is gaunt and pale in the dim light. He coughs and winces, clutching at his side.\n\n"
    "\"A crew of six,\" he gasps. \"They went out to the old wreck in the shallows after salvage. But the tide came up too "
    "fast. I made it back to the shore but the rest... they didn't.\"\n\nThe wreck out in the shallows. The missing crew. "
    "There's something not right about this."
)
T10_LINE = ("I lower my knife, tell Reinald to stay close, and follow the clawed prints deeper into the reeds to find "
            "the beast itself.")
T10_PROSE = (
    "The reeds grow thicker around you, the clawed prints still leading the path. You keep your distance, not wanting to "
    "get any closer to the beast, but needing to find it. Reinald [[C]] stays close behind you, his axe at the ready.\n\n"
    "You push through the curtain of stalks, the air heavy with the salt tang of the marsh. The ground beneath your feet "
    "is spongy and wet, each step a sucking squelch. The prints lead you deeper into the heart of Saltmarrow.\n\n"
    "The reeds thin out ahead and you spot a dark shape huddled in the shadows. It's large, with matted fur and a humped "
    "back. It's the beast you've been tracking.\n\nThe creature doesn't move as you approach, its head bowed low to the "
    "ground. The beast isn't attacking, but instead seems to be... digging.\n\nYou see it now - the beast is burrowing "
    "into the soft earth. It's not a monster, but a creature of the marsh. A saltmarrow boar, rooting for food. You let "
    "out a breath you didn't know you were holding.\n\n\"Easy now,\" you say to Reinald [[C]].\n\nThe reeve nods, but "
    "keeps his axe out, ready. You've both been spooked by the unknown, but now see it for what it is. A normal "
    "saltmarrow boar, no different from those in the marshes.\n\nYou wave your hands to scare it off, but the boar "
    "doesn't budge. It keeps rooting, its snout disappearing into the earth. You approach it cautiously, not wanting to "
    "get any closer than needed.\n\n\"Leave it be,\" Reinald [[C]] says. \"It's just looking for grubs and roots. No need "
    "to chase it down.\"\n\nYou agree and turn to leave the beast to its meal. The reeds part ahead and you spot a figure "
    "standing watch. It's a snare setter, Wat Thatcher, who's been tracking the boar.\n\nHe nods to you in recognition. "
    "\"Thought I heard something,\" he says, eyeing the boar warily. \"Best leave it to its meal. It won't harm you.\"\n\n"
    "You and Reinald [[C]] exchange looks. The beast is just a normal boar, no threat. No need to chase it further."
)


def _world(marsh: str | None = None, marsh_parent_town: bool = True) -> dict[str, int]:
    """Saltmarrow (L1) from a real start; Reinald (C) with the player. With ``marsh``, the marsh place (L2)
    as it stood after T5 in the run (parent Saltmarrow) and the player and Reinald in it."""
    from app import world
    from app.db import connect, init_db

    init_db()
    world.start_playthrough({"player_name": "Isk Tarrow", "start_location": "Saltmarrow", "special_ability_origin": "none"})
    with connect().closing() as conn:
        town = int(conn.execute("SELECT id FROM locations WHERE name = 'Saltmarrow'").fetchone()[0])
        ids = {"town": town}
        here = town
        if marsh:
            cur = conn.execute(
                "INSERT INTO locations (code, name, summary, visit_count, parent_id) VALUES (?, ?, '', 1, ?)",
                (world._next_code(conn, "locations", "L"), marsh, town if marsh_parent_town else 0),
            )
            here = int(cur.lastrowid)
            ids["marsh"] = here
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (here,))
        conn.execute("INSERT INTO npcs (code, location_id, name, role) VALUES ('C', ?, 'Reinald', 'deserter')", (here,))
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


def _here():
    from app.db import connect

    with connect().closing() as conn:
        return conn.execute(
            "SELECT l.id, l.name, l.parent_id FROM player p JOIN locations l ON l.id = p.current_location_id "
            "WHERE p.id = 1").fetchone()


def _place_names() -> list[str]:
    from app.db import connect

    with connect().closing() as conn:
        return [str(r[0]) for r in conn.execute("SELECT name FROM locations ORDER BY id").fetchall()]


def _npc_place(code: str) -> int:
    from app.db import connect

    with connect().closing() as conn:
        row = conn.execute("SELECT location_id FROM npcs WHERE code = ?", (code,)).fetchone()
        return int(row[0]) if row else 0


def _apply(result: dict, line: str, letter: str | None = None, confirm: str = "Yes"):
    from app import where_ended, world
    from app.db import connect

    previous = where_ended.set_ask((lambda s, u: letter if s == "Answer with one letter." else confirm)
                                   if letter else None)
    try:
        if letter:
            with connect().closing() as conn:
                where_ended.ask_where(conn, result, line, result["narration"])
        return world.apply_turn(result, line)
    finally:
        where_ended.set_ask(previous)


class T5ANewPlaceLosesItsPreposition(unittest.TestCase):
    def test_the_leading_preposition_is_not_part_of_the_name(self):
        from app import world

        self.assertEqual(world.humanize_place_name("to Marsh Edge"), "Marsh Edge")
        self.assertEqual(world.humanize_place_name("toward the Old Wreck"), "Old Wreck")
        self.assertEqual(world.humanize_place_name("out to the marsh edge"), "Marsh Edge")
        self.assertEqual(world._clean_place_name("onto the Mudflats."), "Mudflats")
        # A name that starts with a capital is a name, and a bare preposition is left alone.
        self.assertEqual(world.humanize_place_name("At the Sign of the Boar"), "At the Sign of the Boar")
        self.assertEqual(world.humanize_place_name("Into the Deep"), "Into the Deep")
        self.assertEqual(world.humanize_place_name("to"), "To")

    def test_t5_the_walk_out_of_town_files_marsh_edge_outside_the_town(self):
        ids = _world()
        result = {"narration": T5_PROSE, "player": {"move_to_location": "to Marsh Edge", "move_to_location_code": None}}
        with _notes() as ledger:
            _apply(result, T5_LINE)
        names = _place_names()
        self.assertNotIn("to Marsh Edge", names)
        here = _here()
        self.assertIn(here["name"], {"Marsh Edge", "The Marsh Edge"})
        # Out of town: its own place on the map, not a part of Saltmarrow.
        self.assertNotEqual(int(here["parent_id"] or 0), ids["town"])
        decisions = [n.get("decision") for n in ledger.notes]
        self.assertNotIn("new_place_in_town", decisions)
        self.assertIn("new_place_outside_town", decisions)

    def test_a_walk_inside_the_town_is_still_adopted(self):
        # The class's other side: a walk on foot that does not leave the town makes a part of it.
        ids = _world()
        line = "I walk down to the drying racks by the quay to look for Reinald's cousin."
        prose = "You walk down to the Drying Racks by the quay. Nets hang heavy with salt, and gulls quarrel overhead."
        with _notes() as ledger:
            _apply({"narration": prose, "player": {"move_to_location": "to the Drying Racks"}}, line)
        here = _here()
        self.assertEqual(here["name"], "Drying Racks")
        self.assertEqual(int(here["parent_id"] or 0), ids["town"])
        self.assertIn("new_place_in_town", [n.get("decision") for n in ledger.notes])

    def test_leaving_by_the_town_name_reads_as_leaving(self):
        from app import world

        self.assertTrue(world._line_leaves_town(T5_LINE, "Saltmarrow"))
        self.assertTrue(world._line_leaves_town("I walk out of Saltmarrow toward the dunes", "Saltmarrow"))
        self.assertFalse(world._line_leaves_town("I can't leave Saltmarrow yet, so I walk to the quay", "Saltmarrow"))
        self.assertFalse(world._line_leaves_town("I walk to the quay", "Saltmarrow"))


class T10AnUnconfirmedAnswerMovesNobody(unittest.TestCase):
    def _t10(self, letter: str, confirm: str, marsh: str = "to Marsh Edge", parent_town: bool = True):
        ids = _world(marsh, parent_town)
        result = {
            "narration": T10_PROSE,
            "player": {},
            "npcs": [{"code": None, "name": "Wat Thatcher", "race": "human", "location": f"{marsh} [[L2]]",
                      "role": "snare setter", "summary": "", "attitude": "cautious"}],
            "_entity_kinds": {"wat thatcher": "person"},
        }
        with _notes() as ledger:
            state = _apply(result, T10_LINE, letter, confirm)
        return ids, ledger, state

    def test_t10_the_recorded_answers_hold_the_follow_move(self):
        # The run's replies: "B) in Salt" and "Yes, you are" (still in to Marsh Edge).
        ids, ledger, state = self._t10("B) in Salt", "Yes, you are")
        self.assertEqual(int(_here()["id"]), ids["marsh"])
        self.assertEqual(_npc_place("C"), ids["marsh"])
        held = [n for n in ledger.notes if n.get("decision") == "move_held_where_ended_unconfirmed"]
        self.assertEqual(len(held), 1, [n.get("decision") for n in ledger.notes])
        self.assertEqual(held[0]["destination"], "Saltmarrow")
        self.assertEqual(held[0]["rule"], "follow_named")
        movement = (state or {}).get("movement") or {}
        self.assertEqual(movement.get("held_offer"), "Saltmarrow", movement)
        # The snare setter met here is filed here, with the player.
        from app.db import connect

        with connect().closing() as conn:
            wat = conn.execute("SELECT location_id FROM npcs WHERE name = 'Wat Thatcher'").fetchone()
        if wat is not None:
            self.assertEqual(int(wat[0]), ids["marsh"])

    def test_t10_with_the_place_filed_as_the_fix_files_it(self):
        # After the T5 fix the marsh is "Marsh Edge", outside the town: the same replies hold the move too.
        ids, ledger, _state = self._t10("B) outside Marsh", "Yes, you are", "Marsh Edge", parent_town=False)
        self.assertEqual(int(_here()["id"]), ids["marsh"])

    def test_a_confirmed_answer_still_lets_the_follow_move_stand(self):
        # The same turn with the check agreeing ("No": not still in the marsh): the follow move stands.
        ids, ledger, _state = self._t10("B) in Salt", "No")
        self.assertEqual(int(_here()["id"]), ids["town"])
        self.assertNotIn("move_held_where_ended_unconfirmed", [n.get("decision") for n in ledger.notes])


class T6AndT7StayAsRecorded(unittest.TestCase):
    def test_t6_still_here_confirmed_stays(self):
        ids = _world("to Marsh Edge")
        _apply({"narration": T6_PROSE, "player": {}}, T6_LINE, "A) still in", "Yes, you are")
        self.assertEqual(int(_here()["id"]), ids["marsh"])

    def test_t7_an_unconfirmed_b_moves_nobody(self):
        ids = _world("to Marsh Edge")
        with _notes() as ledger:
            _apply({"narration": T7_PROSE, "player": {}}, T7_LINE, "B) in Salt", "Yes, you are")
        self.assertEqual(int(_here()["id"]), ids["marsh"])
        self.assertIn("where_ended_not_confirmed", [n.get("decision") for n in ledger.notes])


if __name__ == "__main__":
    unittest.main()
