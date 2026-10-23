"""#163: Hermes 3 8B writes the turn ops in shapes the parser read as values.

Live replay on the merged code (scratchpad live/integ-r3, 2026-10-24): the
opening's 'NPC_NEW: "NAME" "Theo" "ROLE" "drifter" "LOC" "L1"' (each field label
quoted as its own part) minted a person called "NAME Theo ROLE"; T1's
'MOVE: None', 'LOC_NEW: None', 'EVENT: None' (placeholders for ops the scene did
not need) minted a place and an event called None; and the one man ended as
three rows: A "NAME Theo ROLE", B "Dr. Theo" (NPC_NEW "NAME Dr. Theo ROLE
doctor" did not resolve to the known Theo past the title) and C "Theo" (the
prose's "Dr. Theo, the keeper of this place" read "Theo" as a new keeper).

The drafts below are the real raw_content of those two turns, and the other
op lines are copied from the recorded drafts in the evidence, baseline and
integ-r3 traces. The mocked model answers every ask one way (yes-biased:
"person" / "Yes"; no-biased: "No"): the repairs are the engine's, so the rows
come out the same either way.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-op-shapes-163-"))
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


OPENING_RAW = "===NAR===\nYou wake up to a sky the color of cold steel. The Radiation Fenced Sanctuary is quiet at this hour. You stretch your limbs in the power armor and stand. There's a shop across the way with a sign that says \"Signal Pharmacy\". A drifter with a bandana around their head leans against the wall nearby. They glance up as you step out into the pale dawn light.\n\n===OPS===\nCAST interacting [[L1.drifter]]\nQUEST \"Find a rare ingredient for an elixir\" \"GIVER\" \"the drifter\" \"STEP\" \"buy a map from him\" \"AT\" \"the Signal Pharmacy\" \"REWARD\" \"the elixir\"\nGOAL: \"Find a rare ingredient for an elixir\"\nFOCUS: \"npc\" \"the drifter\"\nSCENE: \"conversation\"\nSUMMARY: \"You meet a drifter who offers to sell you a map to a rare ingredient needed for an elixir.\"\nTALK: \"the drifter\" \"The rare ingredients for an elixir are out near the old tower ruins. But I can save you the trouble. I've got a map that'll lead you right to the heart of the ruins, where you can find the rarest of the rare. For a price, of course.\"\nSKILL: \"Persuasion / Speech\" \"DELTA\" \"true\" \"NOTES\" \"convince the drifter to sell you the map\"\nNPC_NEW: \"NAME\" \"Theo\" \"ROLE\" \"drifter\" \"LOC\" \"L1\"\nJOURNAL: \"quest\" \"Find a rare ingredient for an elixir\" \"The drifter Theo offers to sell me a map that will lead me to rare ingredients needed for an elixir. He wants a price for the map.\""  # noqa: E501
T1_LINE = "I go into the clinic."
T1_RAW = "===NAR===\nYou enter the clinic. It's a small, cluttered room with medical supplies and equipment scattered about. The air is sterile and cold. Behind the counter sits Dr. Theo, the keeper of this place. He looks up as you approach.\n\"Welcome to the clinic,\" Dr. Theo says. \"What brings you here?\"\nYou explain that you've been feeling unwell since arriving in Radiation Fenced Sanctuary. You're worried about radiation exposure and need a checkup.\nDr. Theo nods. \"I see. Well, let's take a look then.\" He pulls out a radiation monitor and scans it over you. \"Hmm, your levels are a bit elevated. Nothing to worry about, but you should be cautious. I'll run some blood tests and a full scan to be sure.\"\nDr. Theo works diligently, checking your vitals and running tests. After an hour or so, he returns with the results. \n\"The good news is there's no signs of acute radiation poisoning,\" Dr. Theo explains. \"But your levels are still higher than ideal. I'd recommend taking it easy for a few days, limiting your exposure to radiation. Stay inside during the day and wear protective gear when you venture out.\"\nYou thank Dr. Theo for the thorough checkup. \"How much do I owe you?\" you ask, reaching for your small bag of coins.\nDr. Theo waves off your payment. \"No need to worry about it. We all have to look out for each other in times like these. Just be careful out there.\"\nYou nod in agreement and exit the clinic, feeling somewhat reassured by Dr. Theo's examination. The radiation levels are a concern, but for now, you plan to heed his advice and take it easy for a few days. The future is uncertain, but for the moment, you're alive and on the move.\n===OPS===\nSUMMARY: \"The player goes into the clinic to deal with whoever works there. Dr. Theo examines the player, checks their radiation levels and gives advice to take it easy and limit exposure to radiation.\"\nSCENE: action\nGOAL: \"To get a checkup and medical advice about possible radiation exposure.\"\nFOCUS: sensory\nNPC_NEW: \"NAME Dr. Theo ROLE doctor\"\nNPC_NOTE: A, \"is the doctor who works at the clinic\"\nTALK: A, \"The player explains symptoms and asks about radiation exposure. Dr. Theo scans and examines the player, then gives medical advice.\"\nGRANT: None\nTAKE: None\nGOLD: None \nXP: None\nHP: None\nKARMA: \"local\", \"Dr. Theo helps the player for free, advising to limit radiation exposure.\"\nMOVE: None\nWALK: None \nLOC_NEW: None\nEVENT: None\nGM: \"The player's radiation levels are elevated but not acute radiation poisoning. Dr. Theo gives advice to take it easy and limit exposure to radiation.\"\nREL: None\nSKILL: None\nCLAIM: None\nJOURNAL: fact, \"Checked into the clinic and examined by Dr. Theo, who gave advice on radiation exposure.\"\nINDEX: location, \"L1\", \"Radiation Fenced Sanctuary clinic\"\nNOTE: \"The clinic is a small room with medical supplies. Dr. Theo is the doctor who works there.\"\nCAST: present, interacting A\nQUEST: None\nQUEST_DONE: None \nLEAD: None"  # noqa: E501


def _turn(ops: str, narration: str = "Theo waits by the wall."):
    from app.turn_dsl import parse_dsl_turn

    return parse_dsl_turn(f"===NAR===\n{narration}\n\n===OPS===\n{ops}\n")


def _fresh_world():
    from app import db, rng, world

    db.init_db()
    rng.reset_seed_cache()
    world.start_playthrough({"player_name": "Will Tanaka", "start_location": "Radiation Fenced Sanctuary",
                             "special_ability_origin": "none"})


class _Biased:
    """A model that answers every ask the same way; every call is kept."""

    def __init__(self, reply: str):
        self.reply = reply
        self.calls: list[str] = []

    def __call__(self, system, user, *, trace=None, usage=None, phase="", max_tokens=None):
        self.calls.append(phase)
        return self.reply

    def identity(self, system, user, *, max_tokens=None, phase=""):
        self.calls.append(phase or "sketch_identity")
        return {"answer": "A" if self.reply != "No" else "new"}


def _play(raws_and_lines, reply):
    """Each draft as play_turn hands it on: parsed, kinds settled, applied. Returns the rows after."""
    from app import db, entity_kinds, sketches, world
    from app.turn_dsl import parse_dsl_turn

    model = _Biased(reply)
    previous_kind = entity_kinds.set_kind_ask(model)
    previous_identity = sketches.set_identity_ask(model.identity)
    try:
        for raw, line in raws_and_lines:
            turn = parse_dsl_turn(raw, line)
            entity_kinds.settle_kinds(turn, line)
            world.apply_turn(turn, line, input_kind="player")
    finally:
        entity_kinds.set_kind_ask(previous_kind)
        sketches.set_identity_ask(previous_identity)
    with db.connect().closing() as conn:
        return {
            "npcs": [(r[0], r[1]) for r in conn.execute("SELECT code, name FROM npcs ORDER BY id")],
            "places": [r[0] for r in conn.execute("SELECT name FROM locations ORDER BY id")],
            "events": [r[0] for r in conn.execute("SELECT title FROM events ORDER BY id")],
        }


# ------------------------------------------------------------- quoted labels


class AQuotedFieldLabelIsTheLabel(unittest.TestCase):
    def test_opening_npc_new_with_every_label_quoted(self):
        npc = _turn('NPC_NEW: "NAME" "Theo" "ROLE" "drifter" "LOC" "L1"')["npcs"][0]
        self.assertEqual((npc["name"], npc["role"], npc["location"]), ("Theo", "drifter", "L1"))
        self.assertEqual(npc["summary"], "")  # was "works at LOC"

    def test_opening_quest_with_every_label_quoted(self):
        mark = _turn(OPENING_RAW.split("===OPS===\n", 1)[1].splitlines()[1])["quest_marks"][0]
        self.assertEqual(mark["title"], "Find a rare ingredient for an elixir")
        self.assertEqual(mark["giver"], "the drifter")
        self.assertEqual(mark["step"], "buy a map from him")  # was "GIVER"
        self.assertEqual(mark["location"], "the Signal Pharmacy")
        self.assertEqual(mark["reward"], "the elixir")

    def test_a_quoted_label_with_its_colon_outside_the_quotes(self):
        # cc87dd29: the step was filed as "giver" and the giver was lost.
        mark = _turn('QUEST: "Survey the Sanctuary", "giver": "Hiro Morgan", "STEP": "Check in with the Repairs and '
                     'the Laundromat"')["quest_marks"][0]
        self.assertEqual((mark["giver"], mark["step"]), ("Hiro Morgan", "Check in with the Repairs and the Laundromat"))

    def test_skill_notes_quoted_after_a_quoted_label(self):
        change = _turn('SKILL: "Persuasion / Speech" "DELTA" "true" "NOTES" "convince the drifter to sell you the map"')[
            "skill_changes"][0]
        self.assertEqual(change["name"], "Persuasion / Speech")
        self.assertEqual(change["notes"], "convince the drifter to sell you the map")

    def test_a_name_label_left_inside_a_person_part(self):
        mark = _turn('QUEST: "job board and personal mysteries" "GIVER NAME Theo" "STEP" "find the rare ingredients for '
                     'an elixir" "AT" "the old tower ruins" "REWARD" "the rare ingredients for an elixir"')["quest_marks"][0]
        self.assertEqual((mark["giver"], mark["step"], mark["location"]),
                         ("Theo", "find the rare ingredients for an elixir", "the old tower ruins"))
        lead = _turn('LEAD: "NAME Yosef Rahman" "TO" "the coast road"')["_dsl"]["leads"][0]
        self.assertEqual(lead, {"npc": "Yosef Rahman", "to": "the coast road"})

    def test_single_quotes_around_a_whole_part(self):
        self.assertEqual(_turn("NPC_NEW: \"NAME: 'Mohan Wong'\"")["npcs"][0]["name"], "Mohan Wong")
        self.assertEqual(_turn("TAKE: \"NAME: 'pills'\"")["inventory_changes"][0]["name"], "pills")
        self.assertEqual(_turn("QUEST: 'Seek medical treatment' GIVER B STEP \"convince Beth to treat your injuries\" AT L3")[
            "quest_marks"][0]["title"], "Seek medical treatment")
        self.assertEqual(_turn("LOC_NEW: 'radiation fenced sanctuary clinic' QTY 1")["locations"][0]["name"],
                         "radiation fenced sanctuary clinic")
        self.assertEqual(_turn("EVENT: 'Explosive Encounter' LOC L3")["events"][0]["title"], "Explosive Encounter")

    def test_a_bare_name_label_before_a_quoted_name(self):
        change = _turn('SKILL: name: "perception", DELTA: band: "small", NOTES: "You notice a faint radioactive glow '
                       'in the distance."')["skill_changes"][0]
        self.assertEqual(change["name"], "perception")  # was "name:"
        self.assertEqual(change["notes"], "You notice a faint radioactive glow in the distance.")

    def test_a_name_with_its_labels_after_a_semicolon(self):
        item = _turn('GRANT: "Ripped Doctor Parts; QTY: 2; BAND: small"')["inventory_changes"][0]
        self.assertEqual(item["name"], "Ripped Doctor Parts")
        self.assertEqual(item["quantity_delta"], 2)

    def test_reverse_quoted_words_that_are_not_the_ops_labels_stay_text(self):
        turn = _turn(
            'NPC_NOTE: B "role"\n'
            'TALK: B "Name"\n'
            'JOURNAL: fact "Step"\n'
            'EVENT: "Giver of the Feast"\n'
            "TAKE: \"Beth's keys\"\n"
            "NOTE: the guards' post by the 'old' gate\n"
            "SUMMARY: You meet Beth. Role: doctor.\n",
        )
        self.assertEqual(turn["index_updates"][0]["summary_append"], "role")
        self.assertEqual(turn["conversations"][0]["summary"], "Name")
        self.assertEqual(turn["journal"][0]["content"], "Step")
        self.assertEqual(turn["events"][0]["title"], "Giver of the Feast")
        self.assertEqual(turn["inventory_changes"][0]["name"], "Beth's keys")
        self.assertIn("guards' post", turn["journal"][1]["content"])
        self.assertEqual(turn["turn_summary"], "You meet Beth. Role: doctor.")
        # A name that only starts with the word stays whole.
        self.assertEqual(_turn('NPC_NEW: NAME "Namesake Bell" ROLE "bell ringer"')["npcs"][0]["name"], "Namesake Bell")


# ------------------------------------------------------------- placeholders


class APlaceholderOpIsNoOp(unittest.TestCase):
    def test_t1_placeholders_mint_nothing(self):
        turn = _turn(T1_RAW.split("===OPS===\n", 1)[1], narration=T1_RAW.split("===OPS===", 1)[0][len("===NAR===\n"):])
        self.assertIsNone(turn["player"]["move_to_location"])
        self.assertEqual(turn["locations"], [])
        self.assertEqual(turn["events"], [])
        self.assertEqual(turn["inventory_changes"], [])
        self.assertEqual(turn["skill_changes"], [])
        self.assertEqual(turn["response_drafts"], [])
        self.assertEqual(turn.get("quest_marks", []), [])
        self.assertEqual(turn["_dsl"].get("leads", []), [])
        dropped = turn["_dsl"]["placeholder_ops"]
        for op in ("GRANT", "TAKE", "MOVE", "WALK", "LOC_NEW", "EVENT", "REL", "SKILL", "CLAIM", "QUEST:", "QUEST_DONE", "LEAD"):
            self.assertTrue(any(line.startswith(op) for line in dropped), op)
        # The ops that carried something are kept.
        self.assertEqual([n["name"] for n in turn["npcs"]], ["Dr. Theo"])
        self.assertTrue(turn["gm_events"])
        self.assertEqual(turn["player"]["karma_visibility"], "local")

    def test_the_drop_is_in_the_ledger(self):
        from app import turn_ledger

        ledger = turn_ledger.Ledger("t")
        token = turn_ledger._CURRENT.set(ledger)
        try:
            _turn("MOVE: None\nEVENT: none\nLOC_NEW: \"none\"\nSCENE: action")
        finally:
            turn_ledger._CURRENT.reset(token)
        notes = [n for n in ledger.notes if n.get("decision") == "placeholder_op_dropped"]
        self.assertEqual(len(notes), 1)
        self.assertIn("MOVE: None", str(notes[0]["lines"]))

    def test_other_placeholder_spellings_and_empty_ops(self):
        turn = _turn('MOVE: null\nLOC_NEW: "N/A"\nEVENT: \nGM: \nCLAIM: \nNOTE: "none"\nQUEST: "none"\nJOURNAL: "fact"\nSCENE: action')
        self.assertIsNone(turn["player"]["move_to_location"])
        self.assertEqual((turn["locations"], turn["events"], turn["gm_events"], turn["response_drafts"], turn["journal"]),
                         ([], [], [], [], []))
        self.assertEqual(turn.get("quest_marks", []), [])

    def test_final_replay_not_present_mints_no_place(self):
        # Final live replay 2026-10-24 T3: "LOC_NEW: not present" made a place "Not",
        # which the interpreter then recorded destroyed.
        turn = _turn('LOC_NEW: not present\nMOVE: nothing\nEVENT: "-"')
        self.assertEqual((turn["locations"], turn["events"]), ([], []))
        self.assertIsNone(turn["player"]["move_to_location"])
        # A real place that holds one of the words is a place.
        turn = _turn('LOC_NEW: "Not Present Tavern", "A bar with no sign."')
        self.assertEqual([loc["name"] for loc in turn["locations"]], ["Not Present Tavern"])

    def test_a_block_of_only_placeholders_is_not_the_wrong_format(self):
        turn = _turn("MOVE: None\nEVENT: None\nQUEST: None")
        self.assertEqual(turn["events"], [])

    def test_reverse_real_values_that_contain_none_are_kept(self):
        turn = _turn(
            'MOVE: "Nonesuch Inn"\n'
            'EVENT: "None of them came back"\n'
            'GOLD: none\n'
            "XP: None\n"
            "KARMA: none\n"
            'NPC_NEW: NAME "Nonna Bell" ROLE baker\n'
        )
        self.assertEqual(turn["player"]["move_to_location"], "Nonesuch Inn")
        self.assertEqual(turn["events"][0]["title"], "None of them came back")
        self.assertEqual(turn["player"]["gold_band"], "none")  # a band word, as the op list says
        self.assertEqual(turn["player"]["xp_band"], "none")
        self.assertEqual(turn["npcs"][0]["name"], "Nonna Bell")
        self.assertNotIn("placeholder_ops", turn["_dsl"])


# ------------------------------------------------------------- the roster


class ATitleBeforeANameIsTheSamePerson(unittest.TestCase):
    def setUp(self):
        _fresh_world()

    def _rows(self, *names_roles):
        from app import db

        with db.connect().closing() as conn:
            conn.execute("DELETE FROM npcs")
            for code, (name, role) in zip("ABCDEF", names_roles):
                conn.execute("INSERT INTO npcs (code, location_id, name, role) VALUES (?, 1, ?, ?)", (code, name, role))

    def _upsert(self, name, role="doctor"):
        from app import db, world

        with db.connect().closing() as conn:
            world._upsert_npc(conn, {"name": name, "role": role, "location": "L1"})
            return [r[0] for r in conn.execute("SELECT name FROM npcs ORDER BY id")]

    def test_dr_theo_is_the_known_theo(self):
        self._rows(("Theo", "drifter"))
        self.assertEqual(self._upsert("Dr. Theo"), ["Theo"])

    def test_a_bare_theo_is_the_known_dr_theo(self):
        self._rows(("Dr. Theo", "doctor"))
        self.assertEqual(self._upsert("Theo", "keeper"), ["Dr. Theo"])

    def test_the_prose_keeper_line_is_not_a_new_person(self):
        from app import world

        text = "Behind the counter sits Dr. Theo, the keeper of this place. He looks up as you approach."
        self.assertEqual(world._introduced_people(text, ["Dr. Theo"]), [])
        self.assertEqual(world._introduced_people(text, []), [{"name": "Theo", "role": "keeper"}])

    def test_reverse_two_titled_theos_resolve_to_nobody(self):
        self._rows(("Dr. Theo", "doctor"), ("Captain Theo", "skipper"))
        self.assertEqual(self._upsert("Theo", "keeper"), ["Dr. Theo", "Captain Theo", "Theo"])

    def test_reverse_another_name_after_the_title_is_someone_else(self):
        self._rows(("Theo", "drifter"))
        self.assertEqual(self._upsert("Dr. Mara"), ["Theo", "Dr. Mara"])
        self._rows(("Theo Marsh", "drifter"))
        self.assertEqual(self._upsert("Dr. Theo"), ["Theo Marsh", "Dr. Theo"])


# ------------------------------------------------------------- end to end


class TheReplayedTurnsFileOneTheoAndNoNone(unittest.TestCase):
    """The real opening and T1 drafts, applied as play_turn applies them."""

    def _check(self, reply):
        _fresh_world()
        rows = _play([(OPENING_RAW, "__opening_scene_request__"), (T1_RAW, T1_LINE)], reply)
        self.assertEqual([name for _, name in rows["npcs"]], ["Theo"])
        self.assertNotIn("None", rows["places"])
        self.assertNotIn("none", [p.lower() for p in rows["places"]])
        self.assertEqual(rows["events"], [])

    def test_yes_biased_model(self):
        self._check("person")
        self._check("Yes")

    def test_no_biased_model(self):
        self._check("No")


if __name__ == "__main__":
    unittest.main()


class TheCastSlotChain(unittest.TestCase):
    """Hermes 3 8B chains CAST slots before the code; every live replay of 2026-10-24 has it."""

    def _cast(self, line):
        from app.turn_dsl import parse_dsl_turn

        return parse_dsl_turn(f"===NAR===\nYou step in. Nate [[A]] looks up.\n\n===OPS===\n{line}\n", "hi")["scene_cast"]

    def test_the_recorded_shapes(self):
        for line in ('CAST:"present interacting A"', "CAST: present, interacting, A", "CAST: present interacting A"):
            cast = self._cast(line)
            self.assertEqual((cast["present"], cast["interacting"]), (["A"], ["A"]), line)

    def test_the_ordinary_shapes_are_unchanged(self):
        self.assertEqual(self._cast("CAST interacting A")["interacting"], ["A"])
        self.assertEqual(self._cast("CAST present A")["present"], ["A"])
        self.assertEqual(self._cast('CAST present "Nate Moss"')["present"], ["Nate Moss"])

    def test_two_groups(self):
        cast = self._cast("CAST: present A B interacting A")
        self.assertEqual((cast["present"], cast["interacting"]), (["A", "B"], ["A"]))
