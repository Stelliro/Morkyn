"""Scene drift (Stell, 2026-10-24: "the story should be told where the player is, fix the drift").

The combined live replay (Hermes 3 8B): T2 "I leave the clinic and creep into the ruined subway tunnel ..."
filed the tunnel (L3) inside the clinic (L2), so the place chain read "inside ... Clinic"; T4 "i search the
dead ghoul" in the tunnel was then written "In the dim glow of the clinic's emergency lanterns" with the
clinic's medic watching. Three fixes, each tested here with the recorded lines and prose:

1. a part of a place reached after leaving the place stood in is not filed inside it;
2. a scene where_ended checks as ending elsewhere, on a line that asked to go nowhere, is re-drafted once
   with one correction riding on the re-draft only (app/scene_drift.py); the better draft is kept;
3. an opening sentence that copies a facts_to_keep entry word for word is dropped.

Run:  .venv/bin/python -m unittest test_scene_drift   (from tests/)
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-scene-drift-"))
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


T2_LINE = "I leave the clinic and creep into the ruined subway tunnel where a pack of ghouls is feeding on a carcass"
T2_PROSE = (
    "You leave the clinic and creep into the ruined subway tunnel where a pack of ghouls is feeding on a carcass. The "
    "early morning sun filters in through cracks in the tunnel ceiling, casting long shadows across the grim scene. The "
    "air reeks of blood and decay. The ghouls are hunched over a large dead horse, ripping at its flesh with their "
    "clawed hands. They look up at you hungrily as you approach, revealing rows of sharp teeth. The largest ghoul snarls "
    "and takes a step towards you, its eyes glowing with a ravenous hunger. You pause, weighing your options, as the "
    "ghouls continue to feast on the carcass just a few feet away."
)
T2_LOC_NEW = [{"name": "ruined subway tunnel", "summary": "Discovered location: ruined subway tunnel"}]
T4_LINE = "i search the dead ghoul"
T4_PROSE = (
    "In the dim glow of the clinic's emergency lanterns, you search the dead ghoul. Its body is already starting to "
    "stiffen. You find a small vial of clear liquid in a pocket, along with a crumpled note that reads \"Meet me at the "
    "old subway entrance at dawn.\" You pocket the note.\n\nThe clinic's medic, an older woman with graying hair, "
    "watches you curiously. \"Find anything useful, there?\" she asks."
)
T4_REDRAFT = (
    "In the dim light of the tunnel you crouch over the dead ghoul. Its body is already starting to stiffen on the "
    "cracked concrete. You find a small vial of clear liquid in a pocket, along with a crumpled note. Water drips "
    "somewhere further down the tunnel."
)


def _world():
    """The combined replay's places: the sanctuary (L1), the clinic in it (L2, kind clinic); player in the clinic."""
    from app import world
    from app.db import connect, init_db

    init_db()
    world.start_playthrough({"player_name": "Vault", "start_location": "Radiation Fenced Sanctuary",
                             "special_ability_origin": "none"})
    with connect().closing() as conn:
        town = int(conn.execute("SELECT current_location_id FROM player").fetchone()[0])
        conn.execute("UPDATE locations SET code = 'L1', name = 'Radiation Fenced Sanctuary' WHERE id = ?", (town,))
        conn.execute("DELETE FROM locations WHERE id != ?", (town,))
        cur = conn.execute("INSERT INTO locations (code, name, summary, visit_count, parent_id, kind) VALUES "
                           "('L2', 'Radiation Fenced Sanctuary Clinic', '', 1, ?, 'clinic')", (town,))
        clinic = int(cur.lastrowid)
        conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (clinic,))
    return town, clinic


def _tunnel_world():
    """As after T2 with the fix: the tunnel (L3) stands in the sanctuary; the player is in it."""
    from app.db import connect

    town, clinic = _world()
    with connect().closing() as conn:
        cur = conn.execute("INSERT INTO locations (code, name, summary, visit_count, parent_id) VALUES "
                           "('L3', 'Ruined Subway Tunnel', 'Discovered location: ruined subway tunnel', 1, ?)", (town,))
        tunnel = int(cur.lastrowid)
        conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (tunnel,))
    return town, clinic, tunnel


def _row(name: str) -> dict:
    from app.db import connect

    with connect().closing() as conn:
        row = conn.execute("SELECT * FROM locations WHERE LOWER(name) = LOWER(?)", (name,)).fetchone()
        return dict(row) if row is not None else {}


def _here() -> dict:
    from app.db import connect

    with connect().closing() as conn:
        return dict(conn.execute(
            "SELECT l.* FROM player p JOIN locations l ON l.id = p.current_location_id WHERE p.id = 1").fetchone())


def _where_model(calls: list | None = None):
    """A mocked turn model for where_ended: the prose that names the clinic ends in it; any other stays."""
    def ask(system: str, user: str) -> str:
        if calls is not None:
            calls.append((system, user))
        drifted = "clinic" in user.split("\n\nIn this text")[0].split("\nIn this text")[0].lower()
        if system == "Answer with one letter.":
            return "B) in Radiation" if drifted else "A) still in"
        return "No." if drifted else "Yes"
    return ask


class APartReachedAfterLeavingIsNotInsideThePlaceLeft(unittest.TestCase):
    def _apply(self, letter: str | None = None, confirm: str = "No."):
        from app import where_ended, world
        from app.db import connect

        result = {"narration": T2_PROSE, "locations": [dict(x) for x in T2_LOC_NEW],
                  "player": {"move_to_location": "ruined subway tunnel"}}
        previous = where_ended.set_ask((lambda s, u: letter if s == "Answer with one letter." else confirm)
                                       if letter else None)
        try:
            if letter:
                with connect().closing() as conn:
                    where_ended.ask_where(conn, result, T2_LINE, T2_PROSE)
            world.apply_turn(result, T2_LINE)
        finally:
            where_ended.set_ask(previous)

    def test_combined_t2_without_the_ask_the_tunnel_stands_in_the_sanctuary(self):
        town, clinic = _world()
        self._apply()
        tunnel = _row("Ruined Subway Tunnel")
        self.assertTrue(tunnel)
        self.assertNotEqual(int(tunnel["parent_id"] or 0), clinic)
        self.assertEqual(int(tunnel["parent_id"] or 0), town)
        self.assertEqual(_here()["name"], "Ruined Subway Tunnel")

    def test_combined_t2_with_the_live_answer_the_player_stands_in_the_tunnel(self):
        # Live: "C) outside Radiation", "No." (confirmed). Review of 5cbf444: the tunnel went into a new
        # "Outside Radiation Fenced Sanctuary" and the venue gate stood the player there, not in the tunnel
        # the prose has them in ("... is entered from Outside ...; the journey ends there.").
        from app.db import connect

        town, clinic = _world()
        self._apply("C) outside Radiation", "No.")
        tunnel = _row("Ruined Subway Tunnel")
        self.assertTrue(tunnel)
        self.assertNotEqual(int(tunnel["parent_id"] or 0), clinic)
        self.assertEqual(int(tunnel["parent_id"] or 0), town)
        self.assertEqual(_here()["name"], "Ruined Subway Tunnel")
        # Settle made no move outside, so the engine's outside place is not made (#46).
        self.assertFalse(_row("Outside Radiation Fenced Sanctuary"))
        with connect().closing() as conn:
            redirects = conn.execute("SELECT content FROM journal WHERE kind = 'venue_redirect'").fetchall()
        self.assertEqual(redirects, [])

    def test_combined_t2_with_a_checked_still_here_keeps_the_line_reader_out(self):
        # A checked "still in the clinic" is the answer the engine acts on: the line's words do not override it.
        town, clinic = _world()
        self._apply("A) still in", "Yes")
        self.assertEqual(int(_row("Ruined Subway Tunnel")["parent_id"] or 0), clinic)

    def test_a_part_reached_without_leaving_is_still_inside(self):
        from app import world

        town, clinic = _world()
        result = {"narration": "You climb down the ladder into the storage cellar. Crates of bandages line the walls.",
                  "locations": [{"name": "storage cellar", "summary": ""}],
                  "player": {"move_to_location": "storage cellar"}}
        world.apply_turn(result, "I climb down into the storage cellar")
        self.assertEqual(int(_row("Storage Cellar")["parent_id"] or 0), clinic)


def _harbour():
    """The reviewer's synthetic world: Saltmarrow (L1) with The Rusty Anchor (tavern), The Mistral (a ship)
    and Old Watchtower in it; Dunmere apart."""
    from app import world
    from app.db import connect, init_db

    init_db()
    world.start_playthrough({"player_name": "Vault", "start_location": "Saltmarrow", "special_ability_origin": "none"})
    with connect().closing() as conn:
        town = int(conn.execute("SELECT current_location_id FROM player").fetchone()[0])
        conn.execute("DELETE FROM locations WHERE id != ?", (town,))
        conn.execute("UPDATE locations SET code = 'L1', name = 'Saltmarrow', parent_id = 0 WHERE id = ?", (town,))
        ids = {"Saltmarrow": town}
        for code, name, parent, kind in (("L2", "The Rusty Anchor", town, "tavern"), ("L3", "The Mistral", town, ""),
                                         ("L4", "Old Watchtower", town, ""), ("L5", "Dunmere", 0, "")):
            cur = conn.execute("INSERT INTO locations (code, name, summary, visit_count, parent_id, kind) "
                               "VALUES (?, ?, '', 1, ?, ?)", (code, name, parent, kind))
            ids[name] = int(cur.lastrowid)
    return ids


class APartIsFiledWhereTheCheckedAnswerAndTheLineAgree(unittest.TestCase):
    """The review of 5cbf444 (scratchpad vdr-scripts/synth.py), each case with its where_ended answer."""

    def _turn(self, start: str, line: str, prose: str, new: str, move: str, letter: str | None, confirm: str = "No."):
        from app import where_ended, world
        from app.db import connect

        ids = _harbour()
        with connect().closing() as conn:
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (ids[start],))
        result = {"narration": prose, "player": {"move_to_location": move or None},
                  "locations": [{"name": new, "summary": ""}] if new else []}
        previous = where_ended.set_ask((lambda s, u: f"{letter})" if s == where_ended.SYSTEM else confirm)
                                       if letter else (lambda s, u: ""))
        try:
            with connect().closing() as conn:
                where_ended.ask_where(conn, result, line, prose)
            world.apply_turn(result, line)
        finally:
            where_ended.set_ask(previous)
        return ids

    def _parent(self, name: str) -> str:
        row = _row(name)
        parent = int(row.get("parent_id") or 0)
        from app.db import connect

        with connect().closing() as conn:
            up = conn.execute("SELECT name FROM locations WHERE id = ?", (parent,)).fetchone()
        return str(up["name"]) if up is not None else ""

    HOLD = ("The Mistral", "I step out of my cabin and go down to the hold",
            "You step out of your cabin and climb down the ladder into the hold. Crates of salt fish are lashed to the "
            "ribs of the ship.", "The Hold", "The Hold")
    COMMON_ROOM = ("The Rusty Anchor", "I leave the tavern's common room and go down to the cellar",
                   "You leave the noise of the common room and take the stair down into the cellar. Casks line the walls.",
                   "Cellar", "Cellar")
    CELLAR = ("The Rusty Anchor", "I head down to the cellar",
              "You take the narrow stair behind the bar down into the cellar. Casks line the damp walls and a lamp swings.",
              "Cellar", "Cellar")

    def test_the_hold_of_the_ship_under_a_checked_still_here(self):
        # 8B run 150's class: out of a cabin is not out of the ship.
        for letter, confirm in (("A", "Yes"), (None, "")):
            self._turn(*self.HOLD, letter, confirm)
            self.assertEqual(self._parent("The Hold"), "The Mistral", (letter, confirm))
            self.assertEqual(_here()["name"], "The Hold")

    def test_the_cellar_left_for_from_the_common_room_is_the_taverns(self):
        for letter, confirm in (("A", "Yes"), (None, "")):
            self._turn(*self.COMMON_ROOM, letter, confirm)
            self.assertEqual(self._parent("Cellar"), "The Rusty Anchor", (letter, confirm))

    def test_a_wrong_up_or_outside_answer_alone_moves_no_part_out(self):
        # B = "in Saltmarrow, outside The Rusty Anchor", C = outside Saltmarrow; the line and prose stay in.
        for letter in ("B", "C"):
            self._turn(*self.CELLAR, letter, "No.")
            self.assertEqual(self._parent("Cellar"), "The Rusty Anchor", letter)
            self.assertEqual(_here()["name"], "Cellar", letter)
            self.assertFalse(_row("Outside Saltmarrow"), letter)

    def test_a_known_place_answer_files_the_part_there_and_the_player_in_it(self):
        # C = "at Old Watchtower": the chamber is the tower's, and the player climbed into it (not stopped at the tower).
        self._turn("Saltmarrow", "I walk to the watchtower and climb to its upper chamber",
                   "You cross the square to the Old Watchtower and climb the spiral stair to the upper chamber. Wind "
                   "whistles through the slits.", "Upper Chamber", "Upper Chamber", "C", "No.")
        self.assertEqual(self._parent("Upper Chamber"), "Old Watchtower")
        self.assertEqual(_here()["name"], "Upper Chamber")
        self.assertFalse(_row("Outside Saltmarrow"))

    def test_leaving_the_town_puts_the_part_outside_it(self):
        # B = outside Saltmarrow, checked; the line leaves the town (no move outside was settled, so no
        # outside place): the mine tunnel is a place of its own, not a part of Saltmarrow, and the player is in it.
        self._turn("Saltmarrow", "I leave town and explore the old mine tunnel to the north",
                   "You leave Saltmarrow behind and follow the cart track north to the mouth of the old mine tunnel. "
                   "Cold air breathes out of it.", "Old Mine Tunnel", "Old Mine Tunnel", "B", "No.")
        self.assertEqual(self._parent("Old Mine Tunnel"), "")
        self.assertEqual(_here()["name"], "Old Mine Tunnel")
        self.assertFalse(_row("Outside Saltmarrow"))


class ALineThatMovesIsNeverRedrafted(unittest.TestCase):
    """The reviewer's corpus (vdr-scripts/asks.py): a line whose act is going somewhere asks to go."""

    MOVES = (
        "I creep into the ruined subway tunnel where a pack of ghouls is feeding on a carcass",
        "i get in my power armor, grab my minigun, and set off to New Vegas to fight a Deathclaw",
        "I set off to New Vegas", "I sneak out the back", "I jump into the river", "I retreat to the surface",
        "I explore the tunnel further", "I continue down the tunnel", "I take the stairs down", "I crawl through the vent",
        "I get out of here", "I push on", "I ask Mara to take me to the clinic", "I head back to the clinic",
        "I flee", "I go upstairs", "I climb out of the tunnel",
    )
    STAYS = (
        "i search the dead ghoul", "i shoot the closest ghoul", "i shoot Dr. Vasilis",
        "i buy some bandages from Dr. Vasilis for 2 gold", "i say hi to Dr. Vasilis", "I look around",
        "I talk to the medic", "I wait for dawn", "I rest here for the night", "a group of 4 ghouls BRUTALLY attack me",
    )

    def test_the_corpus(self):
        from app import world
        from app.db import connect

        _tunnel_world()
        with connect().closing() as conn:
            for line in self.MOVES:
                self.assertTrue(world.line_asks_to_go(conn, line), line)
            for line in self.STAYS:
                self.assertFalse(world.line_asks_to_go(conn, line), line)

    def test_unnamed2_t2_under_a_checked_elsewhere_is_not_redrafted(self):
        # Recorded unnamed2 T2 from the sanctuary; a B/No. answer re-drafted it on 5cbf444.
        from app import scene_drift, where_ended
        from app.db import connect

        town, _clinic = _world()
        with connect().closing() as conn:
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (town,))
        line = "I creep into the ruined subway tunnel where a pack of ghouls is feeding on a carcass"
        calls: list = []
        previous = where_ended.set_ask(lambda s, u: "B)" if s == where_ended.SYSTEM else "No.")
        try:
            first = {"narration": T2_PROSE, "player": {}}
            kept = scene_drift.check(first, line, lambda note: calls.append(note) or {"narration": "x", "player": {}})
        finally:
            where_ended.set_ask(previous)
        self.assertEqual(calls, [])
        self.assertIs(kept, first)


class DriftIsRedraftedOnce(unittest.TestCase):
    def setUp(self):
        from app import where_ended

        self.calls: list = []
        self.previous = where_ended.set_ask(_where_model(self.calls))

    def tearDown(self):
        from app import where_ended

        where_ended.set_ask(self.previous)

    def test_combined_t4_drift_is_detected_and_redrafted(self):
        from app import scene_drift

        _tunnel_world()
        usage: list = []
        trace: list = []
        notes: list = []
        first = {"narration": T4_PROSE, "player": {}}

        def redraft(note: str) -> dict:
            notes.append(note)
            return {"narration": T4_REDRAFT, "player": {}}

        kept = scene_drift.check(first, T4_LINE, redraft, usage=usage, trace=trace)
        self.assertEqual(notes, ["The player is still in Ruined Subway Tunnel; the scene stays there."])
        self.assertEqual(kept["narration"], T4_REDRAFT)
        self.assertEqual(kept["_where_ended"]["choice"]["kind"], "here")
        self.assertEqual(kept["_where_ended"]["text"], T4_REDRAFT)
        record = [r for r in trace if r.get("phase") == "scene_drift"]
        self.assertEqual(len(record), 1)
        self.assertEqual(record[0]["kept"], "redraft")
        self.assertIn("phase", usage[0])
        self.assertEqual([u["phase"] for u in usage], ["scene_drift_redraft"])
        # Two asks on the first draft, two on the re-draft.
        self.assertEqual(len(self.calls), 4)

    def test_a_redraft_that_still_drifts_keeps_the_first(self):
        from app import scene_drift

        _tunnel_world()
        trace: list = []
        calls: list = []
        first = {"narration": T4_PROSE, "player": {}}
        kept = scene_drift.check(first, T4_LINE, lambda note: calls.append(note) or {"narration": T4_PROSE + " ",
                                                                                     "player": {}}, trace=trace)
        self.assertEqual(len(calls), 1)
        self.assertIs(kept, first)
        self.assertEqual([r["kept"] for r in trace if r.get("phase") == "scene_drift"], ["first"])

    def test_a_line_that_goes_somewhere_is_not_redrafted(self):
        from app import scene_drift

        _tunnel_world()
        calls: list = []
        first = {"narration": T4_PROSE, "player": {}}
        kept = scene_drift.check(first, "I head back to the clinic", lambda note: calls.append(note) or {})
        self.assertEqual(calls, [])
        self.assertIs(kept, first)
        # Its answer stays on the turn for play_turn to act on.
        self.assertEqual(kept["_where_ended"]["choice"]["kind"], "up")

    def test_a_scene_that_stays_is_not_redrafted(self):
        from app import scene_drift

        _tunnel_world()
        calls: list = []
        first = {"narration": T4_REDRAFT, "player": {}}
        self.assertIs(scene_drift.check(first, T4_LINE, lambda note: calls.append(note) or {}), first)
        self.assertEqual(calls, [])

    def test_the_correction_rides_on_the_redraft_only(self):
        # Through generate_turn: the first body call has the narrator's own prompts,
        # the re-draft the same prompts with the one correction line at the end.
        from app import llm

        _tunnel_world()
        seen: list = []

        def body(context, player_input, **kw):
            seen.append(kw)
            text = T4_PROSE if len(seen) == 1 else T4_REDRAFT
            kw["trace"].append({"phase": "draft_dsl", "event": "request"})
            return {"narration": text, "player": {}, "_model_trace": kw["trace"], "_model_usage": kw["usage"]}

        with mock.patch.object(llm, "_generate_turn_body", side_effect=body), \
                mock.patch.object(llm, "_run_quest_parser", side_effect=lambda turn, *a, **k: turn):
            result = llm.generate_turn({"current_location": {"name": "Ruined Subway Tunnel", "code": "L3"}}, T4_LINE)
        self.assertEqual(len(seen), 2)
        correction = "The player is still in Ruined Subway Tunnel; the scene stays there."
        self.assertNotIn(correction, seen[0]["dsl_system_prompt"])
        self.assertNotIn(correction, seen[0]["system_prompt"])
        self.assertTrue(seen[1]["dsl_system_prompt"].endswith(correction))
        self.assertTrue(seen[1]["system_prompt"].endswith(correction))
        self.assertEqual(result["narration"], T4_REDRAFT)

    def test_off_switch(self):
        from app import scene_drift

        _tunnel_world()
        calls: list = []
        with mock.patch.dict(os.environ, {"AI_RPG_SCENE_DRIFT": "0"}):
            first = {"narration": T4_PROSE, "player": {}}
            self.assertIs(scene_drift.check(first, T4_LINE, lambda note: calls.append(note) or {}), first)
        self.assertEqual(calls, [])


class TheFactEchoIsDropped(unittest.TestCase):
    FACTS = ["You are in Radiation Fenced Sanctuary [[L1]].", "It is morning, 08:12."]

    def test_the_echoed_opening_is_dropped(self):
        from app.turn_dsl import drop_fact_echo_opening

        text = ("You are in Radiation Fenced Sanctuary [[L1]]. It is morning, 08:12. The fence hums under a white sky, "
                "and two kids chase a dog past the clinic door.\n\nA trader waves at you.")
        fixed, dropped = drop_fact_echo_opening(text, self.FACTS)
        self.assertEqual(len(dropped), 2)
        self.assertTrue(fixed.startswith("The fence hums under a white sky"))
        self.assertTrue(fixed.endswith("A trader waves at you."))

    def test_without_its_code_too(self):
        from app.turn_dsl import drop_fact_echo_opening

        fixed, dropped = drop_fact_echo_opening(
            "You are in Radiation Fenced Sanctuary. The fence hums.", self.FACTS)
        self.assertEqual(fixed, "The fence hums.")
        self.assertEqual(len(dropped), 1)

    def test_an_ordinary_opening_is_kept(self):
        from app.turn_dsl import drop_fact_echo_opening

        for text in ("You are in no hurry. It is morning, 08:12, by the clinic clock.",
                     "The fence hums. You are in Radiation Fenced Sanctuary [[L1]].",
                     "You are in Radiation Fenced Sanctuary [[L1]], where the fence hums all night."):
            fixed, dropped = drop_fact_echo_opening(text, self.FACTS)
            self.assertEqual(fixed, text)
            self.assertEqual(dropped, [])

    def test_a_scene_of_facts_only_is_kept_whole(self):
        from app.turn_dsl import drop_fact_echo_opening

        text = "You are in Radiation Fenced Sanctuary [[L1]]. It is morning, 08:12."
        self.assertEqual(drop_fact_echo_opening(text, self.FACTS), (text, []))

    def test_the_cleanups_drop_it_from_the_turn(self):
        from app import llm

        context = {"current_location": {"name": "Radiation Fenced Sanctuary", "code": "L1"},
                   "world_time": {"hour": 8, "minute_of_hour": 12, "part_of_day": "morning"}}
        text = ("You are in Radiation Fenced Sanctuary [[L1]]. It is morning, 08:12. The fence hums under a white sky, "
                "and two kids chase a dog past the clinic door.")
        turn = {"narration": text, "narration_segments": [{"label": "paragraph", "text": text}]}
        out = llm._drop_fact_echo(turn, context, "test", [])
        self.assertTrue(out["narration"].startswith("The fence hums"))
        self.assertTrue(out["narration_segments"][0]["text"].startswith("The fence hums"))


if __name__ == "__main__":
    unittest.main()
