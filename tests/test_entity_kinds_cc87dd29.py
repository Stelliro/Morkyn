"""Hermes 3 8B run cc87dd29 (Linux .deb playtest): people and places of the wrong kind.

#155 T2: "i get in my power armor, grab my minigun, and set off to New Vegas to
fight a Deathclaw" filed the city as NPC A "New Vegas" (role "minigun cradled"),
read from "New Vegas, the minigun cradled in your armored fist".
#155 T14 (the reverse): a new person was linked with a place code, "Jonah [[L1]]".
#28 T10: NPC_NEW: "NAME: Beth" minted a second person "NAME: Beth" beside Beth [[B]].
#152: a place the player's line names binds to the code the chat showed for it
("I go into the clinic" after "... clinic [[L3]]").

Every quoted string below is copied from the run's traces.
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-cc87dd29-kinds-"))
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


T2_LINE = "i get in my power armor, grab my minigun, and set off to New Vegas to fight a Deathclaw"
# The shipped T2 prose before the engine minted New Vegas and tagged it [[A]].
T2_PROSE = (
    "You stride purposefully towards New Vegas, the minigun cradled in your armored fist, when a sudden ping from "
    "your power armor's readouts pulls you up short. A new message blinks into existence: \"New target detected. "
    "2 miles west. Priority high.\" Your gaze swings automatically to the west, tracking the direction of the "
    "threat.\n\nThe power armor's readouts flicker, a priority alert ping interrupting your march towards New Vegas. "
    "A blinking arrow points 2 miles west, where a new target waits."
)
T2_QUEST_OP = ('QUEST: "Find and fight a Deathclaw in New Vegas", "giver: yourself", "step: find and fight a '
               'Deathclaw", "AT: New Vegas", "REWARD: the satisfaction of a successful fight and experience".')
T10_OPS = (
    "===NAR===\nYou lunge towards Beth, grabbing her arms with one hand and her legs with the other.\n\n"
    "===OPS===\n"
    'SUMMARY: "You killed Beth, the doctor you encountered earlier."\n'
    "SCENE: action\n"
    'FOCUS: "event", "npc"\n'
    'NPC_NEW: "NAME: Beth"\n'
    'NPC_NOTE: "B, Beth, doctor"\n'
    'EVENT: "Beth\'s Murder"\n'
)
T14_PARA = (
    "You follow Doc Beth [[B]] down the path to the clinic, considering her offers. The Radiation Fenced Sanctuary "
    "[[L1]] is starting to feel a bit small. As you approach the clinic, you notice Jonah [[L1]] standing by the "
    "doorway, watching you with a curious expression. He doesn't seem very friendly, his posture suggesting he might "
    "be keeping an eye on Doc Beth [[B]] and her potential new hire."
)
T3_PROSE = (
    "You confidently stride into the bustling Radiation Fenced Sanctuary clinic [[L3]], ready to deal with the "
    "staff. The air is thick with the scent of antiseptic and filled with urgent conversation."
)


def _fresh_world():
    from app import db, rng, world

    db.init_db()
    rng.reset_seed_cache()
    world.start_playthrough({"player_name": "Vault Dweller", "start_location": "Radiation Fenced Sanctuary",
                             "special_ability_origin": "none"})


def _no_ask(*_a, **_k):
    raise AssertionError("no ask expected")


class _Asker:
    def __init__(self, reply: str):
        self.reply = reply
        self.calls: list[tuple[str, str]] = []

    def __call__(self, system, user, *, trace=None, usage=None):
        self.calls.append((system, user))
        return self.reply


class FieldLabelIsNotPartOfAValue(unittest.TestCase):
    """#28: an op's field word and colon inside the quotes label the part."""

    def test_t10_npc_new_name_label(self):
        from app.turn_dsl import parse_dsl_turn

        turn = parse_dsl_turn(T10_OPS)
        self.assertEqual([n["name"] for n in turn["npcs"]], ["Beth"])

    def test_t2_quest_parts_are_read_by_their_labels(self):
        from app.turn_dsl import parse_dsl_turn

        turn = parse_dsl_turn("===NAR===\nYou set off.\n\n===OPS===\n" + T2_QUEST_OP + "\n")
        mark = turn["quest_marks"][0]
        self.assertEqual(mark["location"], "New Vegas")
        self.assertEqual(mark["giver"], "yourself")
        self.assertEqual(mark["step"], "find and fight a Deathclaw")
        self.assertEqual(mark["title"], "Find and fight a Deathclaw in New Vegas")

    def test_other_shapes_of_the_label(self):
        from app.turn_dsl import parse_dsl_turn

        for line in ('NPC_NEW NAME: "Beth" ROLE: doctor', 'NPC_NEW "Name: Beth" "Role: doctor"',
                     'NPC_NEW "name:Beth" ROLE doctor'):
            turn = parse_dsl_turn("===NAR===\nBeth waits.\n\n===OPS===\n" + line + "\n")
            self.assertEqual(turn["npcs"][0]["name"], "Beth", line)
            self.assertEqual(turn["npcs"][0]["role"], "doctor", line)

    def test_a_colon_that_is_not_a_field_stays_text(self):
        from app.turn_dsl import parse_dsl_turn

        turn = parse_dsl_turn(
            "===NAR===\nThe sign reads it.\n\n===OPS===\n"
            'EVENT "Warning: raiders at the gate"\n'
            'SUMMARY: "Summary: you read the sign."\n'
            'FOCUS npc "npc: the guard watches"\n'
        )
        self.assertEqual(turn["events"][0]["title"], "Warning: raiders at the gate")
        self.assertIn("Summary: you read the sign.", turn["turn_summary"])
        self.assertEqual(turn["scene_plan"]["focus_points"][0]["summary"], "npc: the guard watches")

    def test_the_label_free_name_binds_to_the_roster_person(self):
        from app import db, world
        from app.turn_dsl import parse_dsl_turn

        _fresh_world()
        with db.connect().closing() as conn:
            conn.execute("DELETE FROM npcs")
            conn.execute("INSERT INTO npcs (code, location_id, name, role) VALUES ('B', 1, 'Beth', 'doctor')")
            npc = parse_dsl_turn(T10_OPS)["npcs"][0]
            world._upsert_npc(conn, npc)
            names = [r[0] for r in conn.execute("SELECT name FROM npcs")]
        self.assertEqual(names, ["Beth"])


class APlaceTheTurnNamesIsNotAPerson(unittest.TestCase):
    """#155 T2: New Vegas is a place this turn's job names; no ask is needed."""

    def setUp(self):
        from app import entity_kinds

        _fresh_world()
        self.previous = entity_kinds.set_kind_ask(_no_ask)

    def tearDown(self):
        from app import entity_kinds

        entity_kinds.set_kind_ask(self.previous)

    def test_t2_new_vegas_is_not_minted(self):
        from app import db, entity_kinds, world
        from app.turn_dsl import parse_dsl_turn

        turn = parse_dsl_turn(f"===NAR===\n{T2_PROSE}\n\n===OPS===\n{T2_QUEST_OP}\n", T2_LINE)
        kinds = entity_kinds.settle_kinds(turn, T2_LINE)
        self.assertEqual(kinds, {"new vegas": "place"})
        with db.connect().closing() as conn:
            seeded = world._ensure_npcs_from_narration(conn, turn, T2_PROSE, 1)
            names = [r[0] for r in conn.execute("SELECT name FROM npcs")]
        self.assertNotIn("New Vegas", [n.get("name") for n in seeded])
        self.assertNotIn("New Vegas", names)

    def test_the_mint_reads_the_record_on_its_own(self):
        """The offline narrator asks nothing; the turn's own place record still holds."""
        from app import db, world

        turn = {"narration": T2_PROSE, "npcs": [], "quest_marks": [{"op": "QUEST", "location": "New Vegas"}]}
        with db.connect().closing() as conn:
            seeded = world._ensure_npcs_from_narration(conn, turn, T2_PROSE, 1)
        self.assertNotIn("New Vegas", [n.get("name") for n in seeded])


class TheKindAskDecides(unittest.TestCase):
    """#155: with no record, one small ask: person or place."""

    def setUp(self):
        _fresh_world()

    def _settle(self, prose, line, reply):
        from app import entity_kinds

        asker = _Asker(reply)
        previous = entity_kinds.set_kind_ask(asker)
        try:
            turn = {"narration": prose, "npcs": []}
            entity_kinds.settle_kinds(turn, line)
        finally:
            entity_kinds.set_kind_ask(previous)
        return turn, asker

    def _minted(self, turn, prose):
        from app import db, world

        with db.connect().closing() as conn:
            return [n.get("name") for n in world._ensure_npcs_from_narration(conn, turn, prose, 1)]

    def test_t2_without_the_job_asks_and_files_no_person(self):
        from app import entity_kinds

        turn, asker = self._settle(T2_PROSE, T2_LINE, "place")
        self.assertEqual(len(asker.calls), 1)
        system, user = asker.calls[0]
        self.assertEqual(system, entity_kinds.KIND_SYSTEM)
        self.assertTrue(user.endswith('In this text, is "New Vegas" a person or a place?'), user)
        self.assertIn(T2_LINE, user)
        self.assertIn("New Vegas, the minigun cradled", user)
        self.assertNotIn("New Vegas", self._minted(turn, T2_PROSE))

    def test_another_place_phrasing(self):
        prose = "You crest the dune. Haven Ridge, the walled settlement, glows with cookfires."
        turn, asker = self._settle(prose, "i walk toward the lights", "Place.")
        self.assertEqual(len(asker.calls), 1)
        self.assertNotIn("Haven Ridge", self._minted(turn, prose))

    def test_a_person_is_still_minted(self):
        prose = "Mattias Slade, a herbalist with a greying beard, is leaning against the wall."
        turn, asker = self._settle(prose, "i look around", "person")
        self.assertEqual(len(asker.calls), 1)
        self.assertIn("Mattias Slade", self._minted(turn, prose))

    def test_an_unread_reply_keeps_the_old_reading(self):
        turn, _ = self._settle(T2_PROSE, T2_LINE, "I am not sure.")
        self.assertNotIn("_entity_kinds", turn)
        self.assertIn("New Vegas", self._minted(turn, T2_PROSE))

    def test_read_kind(self):
        from app.entity_kinds import read_kind

        self.assertEqual(read_kind(" Place."), "place")
        self.assertEqual(read_kind("PERSON"), "person")
        self.assertEqual(read_kind("person or place"), "")
        self.assertEqual(read_kind(""), "")


class TheOpsAgainstTheRecords(unittest.TestCase):
    """A new person under a place's name, and a new place under a person's name, are asked about."""

    def setUp(self):
        from app import db

        _fresh_world()
        with db.connect().closing() as conn:
            conn.execute("DELETE FROM npcs")
            conn.execute("INSERT INTO npcs (code, location_id, name, role) VALUES ('B', 1, 'Beth', 'doctor')")
            conn.execute("INSERT INTO locations (code, name) VALUES ('L9', 'New Vegas')")

    def _settle(self, turn, reply):
        from app import entity_kinds

        asker = _Asker(reply)
        previous = entity_kinds.set_kind_ask(asker)
        try:
            entity_kinds.settle_kinds(turn, "i look around")
        finally:
            entity_kinds.set_kind_ask(previous)
        return asker

    def test_npc_new_under_a_place_name_is_dropped_when_the_ask_says_place(self):
        from app import db, entity_kinds

        turn = {"narration": "The lights of New Vegas burn on the horizon.", "npcs": [{"name": "New Vegas", "role": "local"}]}
        asker = self._settle(turn, "place")
        self.assertEqual(len(asker.calls), 1)
        with db.connect().closing() as conn:
            kept = entity_kinds.drop_places_from_people(conn, turn["npcs"], turn)
        self.assertEqual(kept, [])

    def test_npc_new_under_a_place_name_stays_when_the_ask_says_person(self):
        from app import db, entity_kinds

        turn = {"narration": "New Vegas, a scarred courier, tips her hat.", "npcs": [{"name": "New Vegas", "role": "courier"}]}
        self._settle(turn, "person")
        with db.connect().closing() as conn:
            kept = entity_kinds.drop_places_from_people(conn, turn["npcs"], turn)
        self.assertEqual([n["name"] for n in kept], ["New Vegas"])

    def test_loc_new_under_a_roster_name(self):
        from app import entity_kinds

        turn = {"narration": "You find Beth by the door.", "npcs": [], "locations": [{"name": "Beth", "summary": ""}]}
        asker = self._settle(turn, "person")
        self.assertEqual(len(asker.calls), 1)
        self.assertTrue(entity_kinds.settled_person(turn, "Beth"))
        turn2 = {"narration": "You find Beth by the door.", "npcs": [], "locations": [{"name": "Beth", "summary": ""}]}
        self._settle(turn2, "place")
        self.assertFalse(entity_kinds.settled_person(turn2, "Beth"))


class TheAskIsTraced(unittest.TestCase):
    """The ask goes through llm._chat_text: prompt, reply and time in the turn's trace and usage."""

    def test_trace_and_usage(self):
        from app import entity_kinds

        trace: list = []
        usage: list = []
        with mock.patch("app.llm._chat_content", return_value="place") as chat:
            reply = entity_kinds._model_ask(entity_kinds.KIND_SYSTEM, "Text: x\nIn this text, is \"x\" a person or a place?",
                                            trace=trace, usage=usage)
        self.assertEqual(reply, "place")
        self.assertEqual(chat.call_args.kwargs.get("max_tokens"), entity_kinds.KIND_MAX_TOKENS)
        self.assertEqual([u["phase"] for u in usage], ["entity_kind"])
        events = [(t["phase"], t["event"]) for t in trace]
        self.assertEqual(events, [("entity_kind", "request"), ("entity_kind", "response")])
        self.assertEqual(trace[0]["system_prompt"], entity_kinds.KIND_SYSTEM)
        self.assertIn("person or a place", trace[0]["user_prompt"])
        self.assertEqual(trace[1]["raw_content"], "place")
        self.assertIn("duration_seconds", trace[1])

    def test_settle_writes_to_the_turns_own_lists(self):
        from app import entity_kinds

        _fresh_world()
        trace: list = []
        usage: list = []
        turn = {"narration": T2_PROSE, "npcs": [], "_model_trace": trace, "_model_usage": usage}
        with mock.patch("app.llm._chat_content", return_value="place"):
            entity_kinds.settle_kinds(turn, T2_LINE)
        self.assertEqual(turn["_entity_kinds"], {"new vegas": "place"})
        self.assertEqual([t["event"] for t in trace if t["phase"] == "entity_kind"], ["request", "response"])
        self.assertEqual([u["phase"] for u in usage], ["entity_kind"])


class AWrongKindCodeIsRetagged(unittest.TestCase):
    """#155 T14: a person linked with a place code gets their own code."""

    def test_t14_jonah(self):
        from app.llm import _repair_prose_entity_labels

        out = _repair_prose_entity_labels(T14_PARA, {"L1": "Radiation Fenced Sanctuary", "B": "Doc Beth", "D": "Jonah"})
        self.assertIn("you notice Jonah [[D]] standing", out)
        self.assertNotIn("Jonah [[L1]]", out)
        self.assertIn("The Radiation Fenced Sanctuary [[L1]] is starting", out)

    def test_a_place_with_a_persons_code(self):
        from app.llm import _repair_prose_entity_labels

        out = _repair_prose_entity_labels("You walk into Saltmarrow [[A]] at dusk.", {"L1": "Saltmarrow", "A": "Tam"})
        self.assertEqual(out, "You walk into Saltmarrow [[L1]] at dusk.")

    def test_a_place_named_for_a_person_keeps_its_code(self):
        from app.llm import _repair_prose_entity_labels

        out = _repair_prose_entity_labels("You board The Mira [[L2]] while Mira [[A]] waves.", {"L2": "The Mira", "A": "Mira"})
        self.assertEqual(out, "You board The Mira [[L2]] while Mira [[A]] waves.")

    def test_apply_turn_retags_a_person_filed_this_turn(self):
        from app import db, world

        _fresh_world()
        with db.connect().closing() as conn:
            conn.execute("INSERT INTO npcs (code, location_id, name, role) VALUES ('B', 1, 'Doc Beth', 'doctor')")
            here = conn.execute("SELECT l.code FROM player p JOIN locations l ON l.id = p.current_location_id").fetchone()[0]
        para = T14_PARA.replace("[[L1]]", f"[[{here}]]")
        turn = {
            "narration": para,
            "npcs": [{"code": None, "name": "Jonah", "race": "human", "location": "", "role": "local"}],
            "self_check": {"passed": True, "issues_found": [], "corrections_made": []},
            "turn_summary": "You meet Doc Beth.",
        }
        world.apply_turn(turn, "i say hi to @Cbeth", input_kind="player")
        with db.connect().closing() as conn:
            jonah = conn.execute("SELECT code FROM npcs WHERE name = 'Jonah'").fetchone()
            shown = conn.execute("SELECT content FROM journal WHERE kind = 'narration' ORDER BY id DESC LIMIT 1").fetchone()
        self.assertIsNotNone(jonah)
        self.assertNotIn(f"Jonah [[{here}]]", shown[0])
        self.assertIn(f"Jonah [[{jonah[0]}]]", shown[0])


class APlaceBindsToTheChatsCode(unittest.TestCase):
    """#152: "I go into the clinic" is the clinic the chat linked last."""

    def setUp(self):
        from app import db

        _fresh_world()
        with db.connect().closing() as conn:
            conn.execute("INSERT INTO locations (code, name, parent_id) VALUES ('L3', 'Radiation Fenced Sanctuary Clinic', 1)")
            conn.execute("INSERT INTO locations (code, name, parent_id) VALUES ('L4', 'Thornford Clinic', 0)")

    def _chat(self, *texts):
        from app import db

        with db.connect().closing() as conn:
            for text in texts:
                conn.execute("INSERT INTO journal (turn, kind, content) VALUES (1, 'narration', ?)", (text,))

    def _resolve(self, line):
        from app import db, world

        with db.connect().closing() as conn:
            rows = conn.execute("SELECT id, code, name, parent_id, kind FROM locations ORDER BY id").fetchall()
            from app import entity_kinds

            chat = entity_kinds.chat_narrations(conn)
            with_chat = world._movement_destination_from_input(rows, line, "Radiation Fenced Sanctuary", chat)
            by_name = world._movement_destination_from_input(rows, line, "Radiation Fenced Sanctuary")
        return (with_chat["code"] if with_chat is not None else None,
                by_name["code"] if by_name is not None else None)

    def test_go_into_the_clinic_after_t3(self):
        self._chat(T3_PROSE)
        bound, by_name = self._resolve("I go into the clinic.")
        self.assertEqual(bound, "L3")
        self.assertIsNone(by_name)  # two clinics: the name alone cannot tell

    def test_the_most_recent_mention_wins(self):
        self._chat(T3_PROSE, "The road bends toward Thornford Clinic [[L4]], its windows dark.")
        self.assertEqual(self._resolve("go to the clinic")[0], "L4")

    def test_a_typed_code_wins(self):
        self._chat(T3_PROSE)
        self.assertEqual(self._resolve("I walk to #L4")[0], "L4")

    def test_not_a_destination(self):
        self._chat(T3_PROSE)
        self.assertIsNone(self._resolve("I leave the clinic")[0])
        self.assertIsNone(self._resolve("I ask Beth about the clinic's records")[0])
        self.assertIsNone(self._resolve("I wait")[0])

    def test_a_person_tagged_with_the_code_gives_no_word(self):
        self._chat("You notice Jonah [[L3]] standing by the doorway.")
        self.assertIsNone(self._resolve("I go to Jonah")[0])

    def test_resolve_movement_uses_the_chat(self):
        from app import db, world

        self._chat(T3_PROSE)
        result = {"player": {}, "narration": "You push open the door and step inside the clinic."}
        with db.connect().closing() as conn:
            report = world.resolve_movement(conn, result, "I go into the clinic.", intent="travel",
                                            narration=result["narration"])
        self.assertEqual(result["player"].get("move_to_location_code"), "L3", report)


if __name__ == "__main__":
    unittest.main()
