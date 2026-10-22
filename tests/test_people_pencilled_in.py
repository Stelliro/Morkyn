"""People pencilled in (app/sketches.py): a new person is a sketch until a later turn brings them back.

Fault rows F26 (and its continuations), F35, F163, F22, F103, F10 in
docs/showcase/run-fault-log-2026-10-18.md: a bad mint used to be a lasting
person. Now a mint is a sketch; it is confirmed when the story brings it back,
merged into a known person when one small ask says it is them, collapsed with a
same-turn twin, or it fades.

Run:  .venv\\Scripts\\python -m unittest tests.test_people_pencilled_in
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-pencilled-"))
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


def _asker(reply):
    calls = []

    def ask(system, user, *, max_tokens, phase):
        calls.append({"system": system, "user": user, "phase": phase})
        if isinstance(reply, Exception):
            raise reply
        return reply

    return ask, calls


def _world():
    """A fresh save: the player at the docks, Fulk Rooke the wherryman known there."""
    from app import rng, world
    from app.db import connect, init_db

    init_db()
    rng.reset_seed_cache()
    world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
    with connect().closing() as conn:
        town = int(conn.execute("SELECT current_location_id FROM player").fetchone()[0])
        conn.execute("INSERT INTO locations (code, name, summary, parent_id) VALUES ('L91', 'The Docks', '', ?)", (town,))
        docks = int(conn.execute("SELECT id FROM locations WHERE code = 'L91'").fetchone()[0])
        conn.execute("DELETE FROM npcs")
        conn.execute("DELETE FROM faded_people")
        conn.execute(
            "INSERT INTO npcs (code, location_id, name, race, role, summary, attitude) "
            "VALUES ('A', ?, 'Fulk Rooke', 'human', 'wherryman', 'A wiry man with a tarred rope coil.', 'neutral')",
            (docks,),
        )
        conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (docks,))
    return town, docks


def _mint(name, role, place_id, summary=""):
    """A person made 'this turn': returns the max id before them."""
    from app import world
    from app.db import connect

    with connect().closing() as conn:
        before = int(conn.execute("SELECT COALESCE(MAX(id), 0) FROM npcs").fetchone()[0])
        code = world._next_alpha_code(conn, "npcs")
        conn.execute(
            "INSERT INTO npcs (code, location_id, name, race, role, summary, attitude) VALUES (?, ?, ?, 'human', ?, ?, 'neutral')",
            (code, place_id, name, role, summary),
        )
    return before


def _settle(turn, narration, before=None, **kw):
    from app import sketches
    from app.db import connect

    with connect().closing() as conn:
        if before is None:
            before = int(conn.execute("SELECT COALESCE(MAX(id), 0) FROM npcs").fetchone()[0])
        return sketches.settle(conn, turn=turn, max_id_before=before, narration=narration, **kw)


def _people():
    from app.db import connect

    with connect().closing() as conn:
        return {str(r["name"]): dict(r) for r in conn.execute("SELECT * FROM npcs").fetchall()}


class AMintIsASketch(unittest.TestCase):
    def setUp(self):
        _, self.docks = _world()

    def test_a_person_made_this_turn_is_pencilled_in_and_known_people_are_not(self):
        before = _mint("Bennet Harrow", "bargeman", self.docks)
        _settle(5, "Bennet Harrow leans on his pole.", before)
        people = _people()
        self.assertEqual(people["Bennet Harrow"]["sketch_turn"], 5)
        self.assertEqual(people["Fulk Rooke"]["sketch_turn"], 0)

    def test_a_sketch_the_prose_brings_back_with_no_one_to_confuse_is_confirmed_without_an_ask(self):
        from app.db import connect

        with connect().closing() as conn:
            conn.execute("DELETE FROM npcs")
        before = _mint("Bennet Harrow", "bargeman", self.docks)
        _settle(5, "Bennet Harrow leans on his pole.", before)
        ask, calls = _asker({"answer": "new"})
        _settle(6, "Bennet Harrow spits into the water and nods at you.", ask=ask)
        self.assertEqual(_people()["Bennet Harrow"]["sketch_turn"], 0)
        self.assertEqual(calls, [])

    def test_a_sketch_never_brought_back_fades(self):
        before = _mint("Ingram Fletcher", "porter", self.docks)
        _settle(5, "A porter hauls a crate.", before)
        for turn in (6, 7, 8, 9):
            _settle(turn, "The tide turns. Gulls wheel over the pilings.")
            self.assertIn("Ingram Fletcher", _people())
        report = _settle(10, "The tide turns. Gulls wheel over the pilings.")
        self.assertNotIn("Ingram Fletcher", _people())
        self.assertEqual(report["faded"], ["Ingram Fletcher"])
        self.assertIn("Fulk Rooke", _people())

    def test_talking_with_them_confirms_them_on_the_turn_they_were_made(self):
        from app.db import connect

        before = _mint("Mabel Tull", "tally clerk", self.docks)
        with connect().closing() as conn:
            npc_id = int(conn.execute("SELECT id FROM npcs WHERE name = 'Mabel Tull'").fetchone()[0])
            conn.execute("INSERT INTO conversations (turn, npc_id, topic, summary) VALUES (5, ?, 'the way', 'Up the hill.')",
                         (npc_id,))
        _settle(5, "The clerk points up the hill.", before, ask=_asker({"answer": "new"})[0])
        for turn in (6, 7, 8, 9, 10, 11):
            _settle(turn, "The tide turns.")
        self.assertEqual(_people()["Mabel Tull"]["sketch_turn"], 0)


class AFadedPersonComesBack(unittest.TestCase):
    """Stell (2026-10-22): a once-met person must not come back as a stranger."""

    def setUp(self):
        from app.db import connect

        _, self.docks = _world()
        before = _mint("Ingram Fletcher", "porter", self.docks, "A stooped man with a hook.")
        with connect().closing() as conn:
            row = conn.execute("SELECT id, code FROM npcs WHERE name = 'Ingram Fletcher'").fetchone()
            self.old_id = int(row["id"])
            conn.execute("INSERT INTO aliases (alias, entity_type, entity_code) VALUES ('the stooped porter', 'npc', ?)",
                         (row["code"],))
        _settle(5, "A porter hauls a crate.", before)
        for turn in (6, 7, 8, 9, 10):
            _settle(turn, "The tide turns.")

    def test_fading_keeps_the_record_out_of_the_world(self):
        from app.db import connect

        self.assertNotIn("Ingram Fletcher", _people())
        with connect().closing() as conn:
            entry = conn.execute("SELECT * FROM faded_people WHERE name = 'Ingram Fletcher'").fetchone()
        self.assertIsNotNone(entry)
        self.assertIn("the stooped porter", json.loads(entry["aliases"]))

    def test_the_same_name_again_brings_back_the_same_person(self):
        from app.db import connect

        before = _mint("Ingram Fletcher", "porter", self.docks)
        report = _settle(14, "Ingram Fletcher sets down his crate.", before)
        people = _people()
        self.assertEqual(people["Ingram Fletcher"]["sketch_turn"], 0)
        self.assertEqual(people["Ingram Fletcher"]["summary"], "A stooped man with a hook.")
        self.assertIn("Ingram Fletcher", report["confirmed"])
        with connect().closing() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM faded_people").fetchone()[0], 0)
            code = conn.execute("SELECT code FROM npcs WHERE name = 'Ingram Fletcher'").fetchone()[0]
            self.assertIsNotNone(conn.execute(
                "SELECT 1 FROM aliases WHERE alias = 'the stooped porter' AND entity_code = ?", (code,)).fetchone())

    def test_a_new_face_in_the_same_trade_here_is_asked_about_them(self):
        before = _mint("Osric Vane", "porter", self.docks)
        from app.db import connect

        _settle(14, "A porter hauls a crate.", before)
        with connect().closing() as conn:
            faded_id = int(conn.execute("SELECT id FROM faded_people WHERE name = 'Ingram Fletcher'").fetchone()[0])
        ask, calls = _asker({"answer": f"X{faded_id}"})
        _settle(15, "Osric Vane wipes his brow and nods to you.", ask=ask)
        self.assertEqual(len(calls), 1)
        self.assertIn("Ingram Fletcher", calls[0]["user"])
        people = _people()
        self.assertNotIn("Osric Vane", people)
        self.assertEqual(people["Ingram Fletcher"]["summary"], "A stooped man with a hook.")
        self.assertEqual(people["Ingram Fletcher"]["sketch_turn"], 0)

    def test_a_name_said_of_someone_absent_does_not_bring_them_back(self):
        before = _mint("Rolf Joliffe", "fisher", self.docks)
        _settle(5, "Rolf Joliffe waves.", before)
        for turn in (6, 7, 8, 9, 10):
            _settle(turn, "There is no sign of Rolf Joliffe. You call out for Rolf Joliffe and no one answers.")
        self.assertNotIn("Rolf Joliffe", _people())

    def test_the_player_naming_them_brings_them_back(self):
        before = _mint("Bennet Harrow", "bargeman", self.docks)
        _settle(5, "Bennet Harrow leans on his pole.", before)
        ask, calls = _asker({"answer": "new"})
        _settle(6, "The water slaps the hull.", player_line="I ask Bennet where the barge is bound.", ask=ask)
        self.assertEqual(_people()["Bennet Harrow"]["sketch_turn"], 0)

    def test_the_figure_phrase_they_were_bound_to_brings_them_back(self):
        from app.db import connect

        with connect().closing() as conn:
            conn.execute("DELETE FROM npcs")
        before = _mint("Edda Crane", "net mender", self.docks)
        with connect().closing() as conn:
            code = conn.execute("SELECT code FROM npcs WHERE name = 'Edda Crane'").fetchone()[0]
            conn.execute("INSERT INTO aliases (alias, entity_type, entity_code) VALUES ('the hooded woman', 'npc', ?)",
                         (code,))
        _settle(5, "A hooded woman mends nets.", before)
        _settle(6, "The hooded woman glances up at you.", ask=_asker({"answer": "new"})[0])
        self.assertEqual(_people()["Edda Crane"]["sketch_turn"], 0)

    def test_a_title_is_not_a_first_name(self):
        before = _mint("Captain Ysolde Marr", "captain", self.docks)
        _settle(5, "Captain Ysolde Marr studies the tide.", before)
        for turn in (6, 7, 8, 9, 10):
            _settle(turn, "Captain Odo shouts from the quay.")
        self.assertNotIn("Captain Ysolde Marr", _people())

    def test_the_giver_of_a_job_never_fades(self):
        from app.db import connect

        before = _mint("Ingram Fletcher", "porter", self.docks)
        _settle(5, "A porter hauls a crate.", before)
        with connect().closing() as conn:
            npc_id = int(conn.execute("SELECT id FROM npcs WHERE name = 'Ingram Fletcher'").fetchone()[0])
            conn.execute("INSERT INTO quests (code, title, status, giver_npc_id) VALUES ('Q1', 'Haul the crates', 'offered', ?)",
                         (npc_id,))
        ask, _calls = _asker({"answer": "new"})
        for turn in (6, 7, 8, 9):
            _settle(turn, "The tide turns.", ask=ask)
        self.assertEqual(_people()["Ingram Fletcher"]["sketch_turn"], 0)


class OneAskDecidesWhoTheyAre(unittest.TestCase):
    def setUp(self):
        _, self.docks = _world()
        before = _mint("Bennet Harrow", "bargeman", self.docks, "A wiry man at the oars.")
        _settle(19, "A wiry man at the oars. Bennet Harrow grins.", before)

    def test_the_ask_is_one_plain_question_over_the_known_people_by_code(self):
        ask, calls = _asker({"answer": "new"})
        _settle(20, "Bennet Harrow pulls the wherry alongside.", ask=ask)
        self.assertEqual(len(calls), 1)
        user = calls[0]["user"]
        self.assertIn("Is this the same person as one of these?", user)
        self.assertIn("A: Fulk Rooke, wherryman", user)
        self.assertTrue(user.rstrip().endswith("Answer a code or new."))
        self.assertEqual(calls[0]["phase"], "sketch_identity")

    def test_a_code_merges_the_sketch_into_that_person(self):
        from app.db import connect

        with connect().closing() as conn:
            sketch_id, code = conn.execute("SELECT id, code FROM npcs WHERE name = 'Bennet Harrow'").fetchone()
            conn.execute("INSERT INTO conversations (turn, npc_id, summary) VALUES (19, ?, 'asked about the tide')",
                         (int(sketch_id),))
        ask, _calls = _asker({"answer": "A"})
        report = _settle(20, f"Bennet Harrow [[{code}]] pulls the wherry alongside.", ask=ask)
        people = _people()
        self.assertNotIn("Bennet Harrow", people)
        self.assertIn("Fulk Rooke", people)
        self.assertEqual(report["renames"], {code: "A"})
        with connect().closing() as conn:
            alias = conn.execute("SELECT entity_code FROM aliases WHERE alias = 'Bennet Harrow'").fetchone()
            talked = conn.execute("SELECT npc_id FROM conversations").fetchone()
            fulk = int(conn.execute("SELECT id FROM npcs WHERE name = 'Fulk Rooke'").fetchone()[0])
        self.assertEqual(alias[0], "A")
        self.assertEqual(int(talked[0]), fulk)

    def test_a_merge_the_engine_cannot_see_is_refused_and_a_merge_is_kept_on_record(self):
        # Side note, 2026-10-22: one wrong model answer must not fuse two real people.
        from app.db import connect

        before = _mint("Maud Kettle", "baker", self.docks, "Flour on her apron and a loud laugh.")
        _settle(20, "Maud Kettle sets out loaves.", before)
        ask, _calls = _asker({"answer": "A"})
        _settle(21, "Maud Kettle waves a floury hand at you.", ask=ask)
        self.assertIn("Maud Kettle", _people())  # a baker is not the wiry wherryman
        with connect().closing() as conn:
            code = conn.execute("SELECT code FROM npcs WHERE name = 'Bennet Harrow'").fetchone()[0]
        _settle(22, f"Bennet Harrow [[{code}]] pulls the wherry alongside.", ask=_asker({"answer": "A"})[0])
        self.assertNotIn("Bennet Harrow", _people())  # both wiry: the engine sees it, the merge stands
        with connect().closing() as conn:
            kept = conn.execute("SELECT record FROM faded_people WHERE name = 'Bennet Harrow'").fetchone()
        self.assertEqual(json.loads(kept[0])["_merged_into"], "A")

    def test_new_keeps_them_as_a_new_person(self):
        ask, _calls = _asker("new")
        _settle(20, "Bennet Harrow pulls the wherry alongside.", ask=ask)
        self.assertEqual(_people()["Bennet Harrow"]["sketch_turn"], 0)
        self.assertIn("Fulk Rooke", _people())

    def test_an_unusable_or_failed_ask_keeps_them_as_new(self):
        ask, _calls = _asker(RuntimeError("model down"))
        _settle(20, "Bennet Harrow pulls the wherry alongside.", ask=ask)
        self.assertEqual(_people()["Bennet Harrow"]["sketch_turn"], 0)

    def test_someone_named_beside_them_in_the_same_prose_is_another_person_and_needs_no_ask(self):
        ask, calls = _asker({"answer": "A"})
        _settle(20, "Bennet Harrow pulls the wherry alongside while Fulk Rooke coils a rope.", ask=ask)
        self.assertEqual(calls, [])
        self.assertIn("Bennet Harrow", _people())


class OneFigureOneSketch(unittest.TestCase):
    """F35: "a figure steps into the light ... the stranger says" minted Alditha and Ellen."""

    PROSE = ("A figure steps into the light at the end of the pier, hood drawn low. "
             "“You’re the one asking about the wreck,” the stranger says.")

    def setUp(self):
        _, self.docks = _world()

    def test_two_unnamed_mints_for_one_figure_collapse_into_the_first(self):
        before = _mint("Alditha", "smuggler", self.docks)
        _mint("Ellen", "local", self.docks)
        report = _settle(32, self.PROSE, before)
        people = _people()
        self.assertIn("Alditha", people)
        self.assertNotIn("Ellen", people)
        self.assertEqual(report["collapsed"], [{"from": "Ellen", "into": "Alditha"}])

    def test_two_people_the_prose_names_are_two(self):
        before = _mint("Alditha", "smuggler", self.docks)
        _mint("Ellen", "net mender", self.docks)
        _settle(32, "Alditha steps off the barge. Ellen looks up from her nets.", before)
        people = _people()
        self.assertIn("Alditha", people)
        self.assertIn("Ellen", people)

    def test_two_figures_shown_keep_two_people(self):
        before = _mint("Alditha", "smuggler", self.docks)
        _mint("Ellen", "net mender", self.docks)
        _settle(32, "A hooded woman waits on the pier. An old man mends nets beside the bollard.", before)
        people = _people()
        self.assertIn("Alditha", people)
        self.assertIn("Ellen", people)

    def test_two_bound_to_the_same_figure_phrase_are_one(self):
        from app.db import connect

        before = _mint("Alditha", "smuggler", self.docks)
        _mint("Ellen", "smuggler", self.docks)
        with connect().closing() as conn:
            ids = {str(r["name"]): int(r["id"]) for r in conn.execute("SELECT id, name FROM npcs")}
        _settle(32, "A hooded woman waits on the pier. An old man mends nets.", before,
                bound_hints={ids["Alditha"]: "A hooded woman", ids["Ellen"]: "a hooded woman"})
        self.assertNotIn("Ellen", _people())

    def test_no_figure_counted_folds_no_one(self):
        before = _mint("Alditha", "smuggler", self.docks)
        _mint("Ellen", "net mender", self.docks)
        _settle(32, "Rain drums on the pier.", before)
        people = _people()
        self.assertIn("Alditha", people)
        self.assertIn("Ellen", people)

    def test_figures_shown_folds_a_vague_definite_figure_into_the_first(self):
        from app.sketches import figures_shown

        self.assertEqual(figures_shown(self.PROSE), 1)
        self.assertEqual(figures_shown("A hooded woman waits. An old man mends nets."), 2)


class TheAnswerIsReadLoosely(unittest.TestCase):
    def test_codes_and_new(self):
        from app.sketches import parse_answer

        self.assertEqual(parse_answer({"answer": "A"}, ["A", "C"]), "A")
        self.assertEqual(parse_answer('{"answer": "C"}', ["A", "C"]), "C")
        self.assertEqual(parse_answer("New", ["A"]), "new")
        self.assertEqual(parse_answer({"answer": "new person"}, ["A"]), "new")
        self.assertEqual(parse_answer({"answer": "B"}, ["A", "C"]), "")
        self.assertEqual(parse_answer({"answer": "A or C"}, ["A", "C"]), "")
        self.assertEqual(parse_answer(None, ["A"]), "")


class ThroughApplyTurn(unittest.TestCase):
    """The pass runs inside apply_turn; a rewind brings back a sketch that faded on the rewound turn."""

    def setUp(self):
        from app import sketches

        _world()
        self.ask, self.calls = _asker({"answer": "new"})
        self._previous = sketches.set_identity_ask(self.ask)

    def tearDown(self):
        from app import sketches

        sketches.set_identity_ask(self._previous)

    def _turn(self, narration, npcs=(), line="I wait."):
        from app import world

        result = {"narration": narration, "npcs": [dict(n) for n in npcs], "self_check": {"passed": True},
                  "turn_summary": "t"}
        world.apply_turn(result, line, input_kind="player")
        return result

    def test_a_minted_person_fades_and_the_rewind_restores_them(self):
        from app import world

        self._turn("Bennet Harrow, a bargeman, leans on his pole and watches you.",
                   [{"name": "Bennet Harrow", "role": "bargeman", "location": "L91"}])
        self.assertGreater(_people()["Bennet Harrow"]["sketch_turn"], 0)
        self._turn("The tide turns. Gulls wheel over the pilings.")
        self._turn("Rain needles the water. The pilings creak.")
        self._turn("Fog rolls in off the harbour mouth.")
        self._turn("A bell tolls somewhere up the hill.")
        self._turn("The light goes grey over the water.")
        self.assertNotIn("Bennet Harrow", _people())
        world.rewind_last_turn()
        self.assertIn("Bennet Harrow", _people())
        self.assertGreater(_people()["Bennet Harrow"]["sketch_turn"], 0)

    def test_a_person_the_next_turn_brings_back_is_kept(self):
        self._turn("Bennet Harrow, a bargeman, leans on his pole and watches you.",
                   [{"name": "Bennet Harrow", "role": "bargeman", "location": "L91"}])
        self._turn("Bennet Harrow shrugs and points upriver.", line="I ask Bennet where he is bound.")
        for text in ("The tide turns.", "Rain needles the water.", "Fog rolls in."):
            self._turn(text)
        self.assertEqual(_people()["Bennet Harrow"]["sketch_turn"], 0)

    def test_the_state_carries_the_sketch_mark_for_the_people_list(self):
        from app import world

        self._turn("Bennet Harrow, a bargeman, leans on his pole and watches you.",
                   [{"name": "Bennet Harrow", "role": "bargeman", "location": "L91"}])
        state = world.get_state()
        row = next(n for place in state["locations"] for n in place.get("npcs") or [] if n["name"] == "Bennet Harrow")
        self.assertGreater(int(row["sketch_turn"]), 0)


if __name__ == "__main__":
    unittest.main()
