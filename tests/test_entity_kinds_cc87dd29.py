"""Hermes 3 8B run cc87dd29 (Linux .deb playtest): people and places of the wrong kind.

#155 T2: "i get in my power armor, grab my minigun, and set off to New Vegas to
fight a Deathclaw" filed the city as NPC A "New Vegas" (role "minigun cradled"),
read from "New Vegas, the minigun cradled in your armored fist".
#155 T14 (the reverse): a new person was linked with a place code, "Jonah [[L1]]".
#28 T10: NPC_NEW: "NAME: Beth" minted a second person "NAME: Beth" beside Beth [[B]];
T14 NPC_NEW: "NAME Marisol Carter ROLE doctor LOC clinic" and T8 "NAME Eli Abbott"
are the same fault without the colon.
#152: a place the player's line goes to binds by reference ("I go into the
clinic" after "... clinic [[L3]]"), but a place named outright wins and only
the player's own going counts.

Every quoted string below from the run is copied from its traces. The mocked
replies are the shapes Hermes 3 8B gave on the live eval (2026-10-23): the kind
ask answered "place" / "Place." / "person" on its first word.
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
T2_QUOTE = "New target detected. 2 miles west. Priority high."
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


class _Asker:
    """A stand-in for the model: one reply per ask (phase), every call kept."""

    def __init__(self, kind: str = "", speaker: str = "", going: str = "", kinds: dict | None = None):
        self.replies = {"entity_kind": kind, "quote_speaker": speaker, "place_going": going}
        self.kinds = kinds or {}
        self.calls: list[tuple[str, str, str]] = []

    def __call__(self, system, user, *, trace=None, usage=None, phase="", max_tokens=None):
        self.calls.append((phase, system, user))
        if phase == "entity_kind":
            for name, reply in self.kinds.items():
                if f'is "{name}" a person' in user:
                    return reply
        reply = self.replies.get(phase, "")
        if isinstance(reply, Exception):
            raise reply
        return reply

    def asked(self, phase):
        return [c for c in self.calls if c[0] == phase]


class _Using:
    def __init__(self, asker):
        self.asker = asker

    def __enter__(self):
        from app import entity_kinds

        self.previous = entity_kinds.set_kind_ask(self.asker)
        return self.asker

    def __exit__(self, *exc):
        from app import entity_kinds

        entity_kinds.set_kind_ask(self.previous)


def _apply(prose, ops, line, asker):
    """Parse the draft, settle before apply_turn as play_turn does, then apply."""
    from app import db, entity_kinds, world
    from app.turn_dsl import parse_dsl_turn

    turn = parse_dsl_turn(f"===NAR===\n{prose}\n\n===OPS===\n{ops}\n", line)
    turn["narration"] = prose
    with _Using(asker):
        entity_kinds.settle_kinds(turn, line)
        world.apply_turn(turn, line, input_kind="player")
    with db.connect().closing() as conn:
        return turn, [r[0] for r in conn.execute("SELECT name FROM npcs")]


# ------------------------------------------------------------------ #28


class FieldLabelIsNotPartOfAValue(unittest.TestCase):
    """#28: an op's own field label inside a value labels that part."""

    def _npc(self, line):
        from app.turn_dsl import parse_dsl_turn

        turn = parse_dsl_turn("===NAR===\nBeth waits.\n\n===OPS===\n" + line + "\n")
        npc = turn["npcs"][0]
        return npc["name"], npc["role"], npc["location"]

    def test_t10_npc_new_name_label(self):
        from app.turn_dsl import parse_dsl_turn

        turn = parse_dsl_turn(T10_OPS)
        self.assertEqual([n["name"] for n in turn["npcs"]], ["Beth"])

    def test_labels_without_a_colon_as_hermes_wrote_them(self):
        # cc87dd29 T14, T8 and the baseline replay T3, exactly as written.
        self.assertEqual(self._npc('NPC_NEW: "NAME Marisol Carter ROLE doctor LOC clinic"'),
                         ("Marisol Carter", "doctor", "clinic"))
        self.assertEqual(self._npc('NPC_NEW: "NAME Eli Abbott" ROLE night clerk LOC "the Rusty Anchor tavern"'),
                         ("Eli Abbott", "night clerk", "the Rusty Anchor tavern"))
        self.assertEqual(self._npc('NPC_NEW: "NAME Jonah Park", ROLE host, LOC inside')[:2], ("Jonah Park", "host"))

    def test_several_labels_in_one_value(self):
        self.assertEqual(self._npc('NPC_NEW: "NAME: Beth, ROLE: doctor"')[:2], ("Beth", "doctor"))
        self.assertEqual(self._npc('NPC_NEW: "NAME: Beth ROLE: doctor LOC: clinic"'), ("Beth", "doctor", "clinic"))
        self.assertEqual(self._npc("NPC_NEW: NAME: Beth ROLE: doctor")[:2], ("Beth", "doctor"))
        self.assertEqual(self._npc('NPC_NEW NAME: "Beth" ROLE: doctor')[:2], ("Beth", "doctor"))
        self.assertEqual(self._npc('NPC_NEW "Name: Beth" "Role: doctor"')[:2], ("Beth", "doctor"))
        self.assertEqual(self._npc('NPC_NEW "name:Beth" ROLE doctor')[:2], ("Beth", "doctor"))

    def test_t2_quest_parts_are_read_by_their_labels(self):
        from app.turn_dsl import parse_dsl_turn

        turn = parse_dsl_turn("===NAR===\nYou set off.\n\n===OPS===\n" + T2_QUEST_OP + "\n")
        mark = turn["quest_marks"][0]
        self.assertEqual(mark["location"], "New Vegas")
        self.assertEqual(mark["giver"], "yourself")
        self.assertEqual(mark["step"], "find and fight a Deathclaw")
        self.assertEqual(mark["title"], "Find and fight a Deathclaw in New Vegas")

    def test_name_label_on_ops_that_open_on_a_name(self):
        from app.turn_dsl import parse_dsl_turn

        turn = parse_dsl_turn('===NAR===\nA bar.\n\n===OPS===\nLOC_NEW: "NAME: The Rusty Bar" "a bar"\nGRANT: "NAME: rusty knife"\n')
        self.assertEqual(turn["locations"][0]["name"], "The Rusty Bar")
        self.assertEqual(turn["inventory_changes"][0]["name"], "rusty knife")

    def test_an_unquoted_label_runs_to_the_next_label(self):
        from app.turn_dsl import parse_dsl_turn

        turn = parse_dsl_turn("===NAR===\nYou snarl.\n\n===OPS===\nKARMA: -2, REASON: starting conflict\n")
        self.assertEqual(turn["player"]["karma_reason"], "starting conflict")

    def test_a_colon_that_is_not_the_ops_field_stays_text(self):
        from app.turn_dsl import parse_dsl_turn

        turn = parse_dsl_turn(
            "===NAR===\nThe sign reads it.\n\n===OPS===\n"
            'EVENT "Warning: raiders at the gate"\n'
            'SUMMARY: "Summary: you read the sign."\n'
            'FOCUS npc "npc: the guard watches"\n'
            "JOURNAL: fact, Name: the doctor is Beth\n"
            "TALK: B, Name: what is yours?\n"
            'NPC_NEW: "AT: the gate"\n'
        )
        self.assertEqual(turn["events"][0]["title"], "Warning: raiders at the gate")
        self.assertIn("Summary: you read the sign.", turn["turn_summary"])
        self.assertEqual(turn["scene_plan"]["focus_points"][0]["summary"], "npc: the guard watches")
        self.assertEqual(turn["journal"][0]["content"], "Name: the doctor is Beth")
        self.assertEqual(turn["conversations"][0]["summary"], "Name: what is yours?")
        self.assertEqual(turn["npcs"][0]["name"], "AT: the gate")
        turn = parse_dsl_turn("===NAR===\nYou meet Beth.\n\n===OPS===\nSUMMARY: You meet Beth. Role: doctor.\n")
        self.assertEqual(turn["turn_summary"], "You meet Beth. Role: doctor.")

    def test_the_field_table_is_read_from_the_op_list(self):
        from app import turn_dsl

        self.assertEqual(turn_dsl._OP_FIELDS["NPC_NEW"], {"NAME", "ROLE", "LOC", "ATTITUDE", "RACE", "RANK"})
        self.assertEqual(turn_dsl._OP_FIELDS["QUEST"], {"GIVER", "STEP", "AT", "REWARD"})
        self.assertNotIn("JOURNAL", turn_dsl._OP_FIELDS)
        self.assertEqual(turn_dsl._NAME_FIRST_OPS, {"GRANT", "TAKE", "LOC_NEW", "SKILL"})

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


# ------------------------------------------------------------------ #155


class TheAskDecidesNotTheOps(unittest.TestCase):
    """#155: every new name the turn would file is asked about; the model's ops are candidates."""

    def setUp(self):
        _fresh_world()

    def test_t2_real_ops_ask_once_and_file_no_one(self):
        """The real T2 draft: New Vegas is a place, and the armour's readout seeds no stranger."""
        from app import entity_kinds

        asker = _Asker(kind="place", speaker="No")
        turn, names = _apply(T2_PROSE, T2_QUEST_OP, T2_LINE, asker)
        kind_calls = asker.asked("entity_kind")
        self.assertEqual(len(kind_calls), 1)  # the QUEST AT op did not decide on its own
        self.assertEqual(kind_calls[0][1], entity_kinds.KIND_SYSTEM)
        self.assertTrue(kind_calls[0][2].endswith('In this text, is "New Vegas" a person or a place?'))
        self.assertIn(T2_LINE, kind_calls[0][2])
        speaker = asker.asked("quote_speaker")
        self.assertEqual(len(speaker), 1)
        self.assertEqual(speaker[0][1], "Answer yes or no.")
        self.assertTrue(speaker[0][2].endswith(f'In this text, does a person say "{T2_QUOTE}"?'), speaker[0][2])
        self.assertIn("A new message blinks into existence", speaker[0][2])
        self.assertEqual(names, [])
        self.assertEqual(turn.get("_quotes_not_spoken"), [T2_QUOTE])

    def test_a_quote_a_person_says_still_seeds_a_face(self):
        """The reverse: a stranger's line with nobody filed still gets a face."""
        from app import db, world

        prose = 'You reach the gate at dusk. A voice calls down from the wall: "Who goes there? State your name."'
        asker = _Asker(speaker="Yes")
        with _Using(asker):
            from app import entity_kinds

            turn = {"narration": prose, "npcs": []}
            entity_kinds.settle_kinds(turn, "i walk to the gate")
        self.assertEqual(len(asker.asked("quote_speaker")), 1)
        self.assertNotIn("_quotes_not_spoken", turn)
        with db.connect().closing() as conn:
            seeded = world._ensure_npcs_from_narration(conn, turn, prose, 1)
        self.assertEqual(len(seeded), 1)

    def test_a_job_at_a_person_does_not_drop_the_person(self):
        """QUEST AT "Mattias Slade" over 'Mattias Slade, the courier': the ask says person, he is filed."""
        prose = "Beth points at the map. \"Go to Goodsprings.\" Mattias Slade, the courier, nods along."
        asker = _Asker(kind="person")
        _, names = _apply(prose, 'QUEST: "Deliver the package", "AT: Mattias Slade"', "I ask about the job", asker)
        self.assertIn("Mattias Slade", names)
        self.assertEqual(len(asker.asked("entity_kind")), 1)

    def test_a_new_person_op_under_a_place_name(self):
        """NPC_NEW "Megaton" on 'I travel to Megaton': no record names it, the ask does."""
        prose = "You set off along the cracked highway toward Megaton. The wind howls across the dunes."
        asker = _Asker(kind="place")
        _, names = _apply(prose, 'NPC_NEW: "Megaton", "settlement"', "I travel to Megaton", asker)
        self.assertNotIn("Megaton", names)
        self.assertEqual(len(asker.asked("entity_kind")), 1)

    def test_people_the_prose_introduces_are_filed_on_person(self):
        prose = "Mattias Slade, a herbalist with a greying beard, leans against the wall. Rosa Vance, the smith, hammers nearby."
        asker = _Asker(kind="person")
        _, names = _apply(prose, "", "I look around", asker)
        self.assertIn("Mattias Slade", names)
        self.assertIn("Rosa Vance", names)

    def test_offline_narrator_ops_are_records(self):
        """The offline narrator's ops are the engine's own: they decide, and nothing is asked."""
        from app import db, entity_kinds, world
        from app.turn_dsl import parse_dsl_turn

        turn = parse_dsl_turn(f"===NAR===\n{T2_PROSE}\n\n===OPS===\n{T2_QUEST_OP}\n", T2_LINE)
        asker = _Asker(kind="person")
        with _Using(asker):
            kinds = entity_kinds.settle_kinds(turn, T2_LINE, ask=False)
        self.assertEqual(asker.calls, [])
        self.assertEqual(kinds, {"new vegas": "place"})
        with db.connect().closing() as conn:
            seeded = world._ensure_npcs_from_narration(conn, turn, T2_PROSE, 1)
        self.assertNotIn("New Vegas", [n.get("name") for n in seeded])

    def test_an_unread_reply_keeps_the_old_reading(self):
        from app import db, entity_kinds, world

        for reply in ("I am not sure.", "", RuntimeError("model down")):
            turn = {"narration": T2_PROSE, "npcs": []}
            with _Using(_Asker(kind=reply, speaker="")):
                entity_kinds.settle_kinds(turn, T2_LINE)
            self.assertNotIn("_entity_kinds", turn)
            with db.connect().closing() as conn:
                names = [n.get("name") for n in world._ensure_npcs_from_narration(conn, turn, T2_PROSE, 1)]
            self.assertIn("New Vegas", names, reply)
            with db.connect().closing() as conn:
                conn.execute("DELETE FROM npcs WHERE name = 'New Vegas'")

    def test_read_kind_and_yes_no(self):
        from app.entity_kinds import read_kind, read_yes_no

        self.assertEqual(read_kind(" Place."), "place")
        self.assertEqual(read_kind("PERSON"), "person")
        self.assertEqual(read_kind("You stride towards the place"), "")
        self.assertEqual(read_kind(""), "")
        self.assertIs(read_yes_no("No, Beth does not speak"), False)
        self.assertIs(read_yes_no("Yes."), True)
        self.assertIsNone(read_yes_no("Nobody knows"))


class TheOpsAgainstTheRecords(unittest.TestCase):
    """A new person under a place's name, and a new place under a person's name."""

    def setUp(self):
        from app import db

        _fresh_world()
        with db.connect().closing() as conn:
            conn.execute("DELETE FROM npcs")
            conn.execute("INSERT INTO npcs (code, location_id, name, role) VALUES ('B', 1, 'Beth', 'doctor')")
            conn.execute("INSERT INTO locations (code, name) VALUES ('L9', 'New Vegas')")

    def _settle(self, turn, reply):
        from app import entity_kinds

        asker = _Asker(kind=reply)
        with _Using(asker):
            entity_kinds.settle_kinds(turn, "i look around")
        return asker

    def test_npc_new_under_a_place_name(self):
        from app import db, entity_kinds

        turn = {"narration": "The lights of New Vegas burn on the horizon.", "npcs": [{"name": "New Vegas", "role": "local"}]}
        self.assertEqual(len(self._settle(turn, "place").asked("entity_kind")), 1)
        with db.connect().closing() as conn:
            self.assertEqual(entity_kinds.drop_places_from_people(conn, turn["npcs"], turn), [])
        turn = {"narration": "New Vegas, a scarred courier, tips her hat.", "npcs": [{"name": "New Vegas", "role": "courier"}]}
        self._settle(turn, "person")
        with db.connect().closing() as conn:
            kept = entity_kinds.drop_places_from_people(conn, turn["npcs"], turn)
        self.assertEqual([n["name"] for n in kept], ["New Vegas"])

    def test_a_roster_person_in_the_ops_is_not_asked_about(self):
        turn = {"narration": "Beth waves.", "npcs": [{"name": "Beth", "role": "doctor"}]}
        self.assertEqual(self._settle(turn, "person").asked("entity_kind"), [])

    def test_loc_new_under_a_roster_name(self):
        from app import entity_kinds

        turn = {"narration": "You find Beth by the door.", "npcs": [], "locations": [{"name": "Beth", "summary": ""}]}
        self.assertEqual(len(self._settle(turn, "person").asked("entity_kind")), 1)
        self.assertTrue(entity_kinds.settled_person(turn, "Beth"))
        turn2 = {"narration": "You find Beth by the door.", "npcs": [], "locations": [{"name": "Beth", "summary": ""}]}
        self._settle(turn2, "place")
        self.assertFalse(entity_kinds.settled_person(turn2, "Beth"))


class TheAsksAreTraced(unittest.TestCase):
    """The asks go through llm._chat_text: prompt, reply and time in the turn's trace and usage."""

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
        self.assertEqual([(t["phase"], t["event"]) for t in trace], [("entity_kind", "request"), ("entity_kind", "response")])
        self.assertEqual(trace[0]["system_prompt"], entity_kinds.KIND_SYSTEM)
        self.assertEqual(trace[1]["raw_content"], "place")
        self.assertIn("duration_seconds", trace[1])

    def test_settle_writes_every_ask_to_the_turns_own_lists(self):
        from app import entity_kinds

        _fresh_world()
        trace: list = []
        usage: list = []
        turn = {"narration": T2_PROSE, "npcs": [], "_model_trace": trace, "_model_usage": usage}

        def _reply(system, user, **_k):
            return "place" if "person or a place" in user else "No."

        with mock.patch("app.llm._chat_content", side_effect=_reply):
            entity_kinds.settle_kinds(turn, T2_LINE)
        self.assertEqual(turn["_entity_kinds"], {"new vegas": "place"})
        self.assertEqual([u["phase"] for u in usage], ["entity_kind", "quote_speaker"])
        self.assertEqual([(t["phase"], t["event"]) for t in trace],
                         [("entity_kind", "request"), ("entity_kind", "response"),
                          ("quote_speaker", "request"), ("quote_speaker", "response")])


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


# ------------------------------------------------------------------ #152


class APlaceBindsByReference(unittest.TestCase):
    """#152: a typed code or the chat's code, checked by one ask; a place named outright wins."""

    def setUp(self):
        from app import db

        _fresh_world()
        with db.connect().closing() as conn:
            conn.execute("INSERT INTO locations (code, name, parent_id) VALUES ('L3', 'Radiation Fenced Sanctuary Clinic', 1)")
            conn.execute("INSERT INTO locations (code, name, parent_id) VALUES ('L4', 'Thornford Clinic', 0)")
            conn.execute("INSERT INTO locations (code, name, parent_id) VALUES ('L5', 'Thornford', 0)")
            conn.execute("INSERT INTO journal (turn, kind, content) VALUES (1, 'narration', ?)", (T3_PROSE,))

    def _settle(self, line, going="Yes"):
        from app import entity_kinds

        asker = _Asker(going=going)
        result: dict = {"player": {}}
        with _Using(asker):
            entity_kinds.settle_place_reference(result, line)
        return result.get("_place_by_reference", ""), asker.asked("place_going")

    def test_go_into_the_clinic_after_t3(self):
        from app import db, world

        code, asks = self._settle("I go into the clinic.")
        self.assertEqual(code, "L3")
        self.assertEqual(asks[0][1], "Answer yes or no.")
        self.assertEqual(asks[0][2], "The player wrote: I go into the clinic.\nIs the player going to the clinic?")
        with db.connect().closing() as conn:
            rows = conn.execute("SELECT id, code, name, parent_id, kind FROM locations ORDER BY id").fetchall()
        # Two clinics: by name alone the line names neither.
        self.assertIsNone(world._movement_destination_from_input(rows, "I go into the clinic.", "Radiation Fenced Sanctuary"))

    def test_a_place_named_outright_wins_and_nothing_is_asked(self):
        for line in ("I go to the Thornford Clinic.", "go to the Thornford clinic, not the sanctuary one",
                     "I walk from #L3 to Thornford", "I leave #L3 and head for Thornford"):
            code, asks = self._settle(line)
            self.assertEqual((code, asks), ("", []), line)

    def test_only_the_players_own_going_binds(self):
        # The going ask says no (another person goes, or the line only points).
        for line in ("I tell Beth to go to the clinic", "I shout to the clinic staff", "I point to the clinic"):
            code, asks = self._settle(line, going="No.")
            self.assertEqual(code, "", line)
            self.assertEqual(len(asks), 1, line)

    def test_a_typed_code_is_asked_by_its_name(self):
        code, asks = self._settle("I walk to #L4", going="Yes")
        self.assertEqual(code, "L4")
        self.assertEqual(asks[0][2], "The player wrote: I walk to Thornford Clinic\nIs the player going to Thornford Clinic?")

    def test_a_place_left_is_no_candidate(self):
        code, asks = self._settle("I walk out of #L3")
        self.assertEqual((code, asks), ("", []))

    def test_an_unread_reply_binds_nothing(self):
        code, _ = self._settle("I go into the clinic.", going="Perhaps")
        self.assertEqual(code, "")

    def test_a_person_tagged_with_the_code_gives_no_word(self):
        from app import db

        with db.connect().closing() as conn:
            conn.execute("DELETE FROM journal")
            conn.execute("INSERT INTO journal (turn, kind, content) VALUES (1, 'narration', 'You notice Jonah [[L3]] standing by the doorway.')")
        self.assertEqual(self._settle("I go to Jonah"), ("", []))

    def test_resolve_movement_end_to_end(self):
        from app import db, entity_kinds, world

        narr = "You push open the door and step inside the clinic."
        result = {"player": {}, "narration": narr}
        with _Using(_Asker(going="Yes")):
            entity_kinds.settle_kinds(result, "I go into the clinic.")
        with db.connect().closing() as conn:
            report = world.resolve_movement(conn, result, "I go into the clinic.", intent="travel", narration=narr)
        self.assertEqual(result["player"].get("move_to_location_code"), "L3", report)

    def test_resolve_movement_keeps_the_model_move_to_the_named_place(self):
        """'I go to the Thornford Clinic.' with MOVE L4: no reference overrides it."""
        from app import db, entity_kinds, world

        narr = "You set off down the road toward Thornford Clinic [[L4]]."
        result = {"player": {"move_to_location_code": "L4"}, "narration": narr}
        with _Using(_Asker(going="Yes")):
            entity_kinds.settle_kinds(result, "I go to the Thornford Clinic.")
        self.assertNotIn("_place_by_reference", result)
        with db.connect().closing() as conn:
            world.resolve_movement(conn, result, "I go to the Thornford Clinic.", intent="travel", narration=narr)
        self.assertEqual(result["player"].get("move_to_location_code"), "L4")

    def test_telling_someone_else_to_go_leaves_the_player(self):
        from app import db, entity_kinds, world

        narr = "Beth nods and hurries off toward the clinic while you wait by the gate."
        result = {"player": {}, "narration": narr}
        with _Using(_Asker(going="No")):
            entity_kinds.settle_kinds(result, "I tell Beth to go to the clinic")
        with db.connect().closing() as conn:
            world.resolve_movement(conn, result, "I tell Beth to go to the clinic", intent="social", narration=narr)
        self.assertNotEqual(result["player"].get("move_to_location_code"), "L3")


if __name__ == "__main__":
    unittest.main()
