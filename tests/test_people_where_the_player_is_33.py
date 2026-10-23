"""Where the player is, the people met are (#33; CLAUDE.md, Design decisions, 2026-10-24).

"play state needs to be in the same location as npc and hadded to the llm to
ensure that the llm knows where the player is". A person the player meets is
filed at the player's place (app/whereabouts.py), and the narrator is told
plainly where the player is (prompts._place_view "player_is_in").

The strings are the final live replay of 2026-10-24 (Hermes 3 8B, scratchpad
live/final, turns/001.json and 003.json; data/model_traces
turn-0112fac5-000002/-000004): T1 "I go into the clinic." showed Nate [[A]] at
his workbench inside the clinic while his row (a sketch from the opening) stayed
in the town, so at T3 "i shoot Nate" the attack ask found nobody at the
player's place. And integ-r4 T1 (turn-6b5a9245-000002): Dr. Vasilis seeded in
the clinic the player walked into.

The model is mocked. The one ask this path uses is the interpreter's measured
hold ask, "Does <Name> say or do anything in it?" (Hermes 3 8B: 94%, no false
no; docs/showcase/ask-live-eval-2026-10-24.md); its mocked reply is the right
answer for the passage.

Run:  cd tests && python -m unittest test_people_where_the_player_is_33
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-where33-test-"))
_ENV = {
    "AI_RPG_DB": str(_TMP / "world.db"),
    "AI_RPG_PACK_DIR": str(_TMP / "packs"),
    "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
    "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
    "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
    "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
    "AI_RPG_CAMPAIGN_SLOTS": str(_TMP / "slots"),
}
os.environ.update(_ENV)

from app import attack_intent, db, interpreter, llm, prompts, whereabouts, world  # noqa: E402

I = interpreter

TOWN = "Radiation Fenced Sanctuary"
CLINIC = "Radiation Fenced Sanctuary Clinic"

# live/final turns/001.json: "I go into the clinic." (the shipped narration)
FINAL_T1_LINE = "I go into the clinic."
FINAL_T1 = (
    "You step into the clinic, a sterile room lined with empty cots on the far wall. The door scrapes shut behind you "
    "as you cross the threshold. Morning light filters in through grimy windows, casting a dull glow across the room."
    "\n\n"
    "Nate [[A]], the field tech, looks up from his workbench on the opposite side of the clinic. His brow furrows as he "
    "sets down his tools. \"Who goes there?\" he calls out, a hint of wariness in his voice. \"State your business.\""
)
FINAL_T3_LINE = "i shoot Nate"

# integ-r4 turns/001.json: "I go into the clinic." with the doctor seeded from the prose
R4_T1 = (
    'You enter the clinic, a small stone building with a sign out front that reads "Dr. Vasilis - Healing for a '
    'Price." The air inside is sterile, with the sharp scent of disinfectant. Behind the counter sits Dr. Vasilis, '
    "a middle-aged man with graying hair. He looks up at you wearily as you approach.\n\n"
    '"Another adventurer in need of healing," Dr. Vasilis says with a sigh. "I can\'t say I\'m surprised. '
    'The price of survival these days is steep."\n\n'
    '"What brings you here, traveler?" he asks.'
)

ACTS = "say or do anything in it"


class Model:
    """Replies to the interpreter's asks by what they ask ("No" unless given)."""

    def __init__(self, acts: dict[str, str] | None = None):
        self.acts = dict(acts or {})  # name -> reply to "Does <name> say or do anything in it?"
        self.calls: list[str] = []

    def __call__(self, system: str, user: str, **kwargs) -> str:
        self.calls.append(user)
        if ACTS in user:
            for name, reply in self.acts.items():
                if f"Does {name} say or do anything" in user:
                    return reply
        return "No"

    def asked_about(self, name: str) -> bool:
        return any(f"Does {name} say or do anything" in c for c in self.calls)


def _fresh_world() -> int:
    os.environ.update(_ENV)
    assert str(db.db_path()).startswith(str(_TMP)), db.db_path()
    db.init_db()
    world.start_playthrough({"player_name": "Will Tanaka", "start_location": TOWN, "special_ability_origin": "none"})
    return _here_id()


def _here_id() -> int:
    with db.connect().closing() as conn:
        return int(conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()[0])


def _add_place(name: str, parent_id: int = 0, kind: str = "") -> tuple[int, str]:
    with db.connect().closing() as conn:
        n = conn.execute("SELECT COALESCE(MAX(id), 0) FROM locations").fetchone()[0]
        code = f"L{int(n) + 1}"
        cur = conn.execute(
            "INSERT INTO locations (code, name, summary, visit_count, parent_id, kind) VALUES (?, ?, '', 0, ?, ?)",
            (code, name, int(parent_id), kind),
        )
        conn.commit()
        return int(cur.lastrowid), code


def _add_npc(name: str, location_id: int, role: str = "local", sketch_turn: int = 0) -> str:
    with db.connect().closing() as conn:
        code = world._next_alpha_code(conn, "npcs")
        conn.execute(
            "INSERT INTO npcs (code, location_id, name, role, pronouns, sketch_turn) VALUES (?, ?, ?, ?, 'he', ?)",
            (code, int(location_id), name, role, int(sketch_turn)),
        )
        conn.commit()
        return code


def _place_of(code: str) -> int:
    with db.connect().closing() as conn:
        return int(conn.execute("SELECT location_id FROM npcs WHERE code = ?", (code,)).fetchone()[0] or 0)


def _place_of_name(name: str) -> int | None:
    with db.connect().closing() as conn:
        row = conn.execute("SELECT location_id FROM npcs WHERE name = ? COLLATE NOCASE", (name,)).fetchone()
        return int(row[0] or 0) if row else None


def _turn(narration: str, *, move_to: str = "", npcs: list | None = None, cast: dict | None = None) -> dict:
    return {
        "scene_plan": {"goal": "look", "focus_points": []},
        "narration_segments": [{"label": "scene", "text": narration}],
        "narration": narration,
        "player": {"move_to_location": move_to} if move_to else {},
        "npcs": list(npcs or []),
        "self_check": {"passed": True, "issues_found": [], "corrections_made": []},
        "turn_summary": "a beat",
        "scene_focus": "action",
        "scene_cast": cast or {"present": [], "interacting": [], "off": []},
        "_interpreter_pending": {"config": {}},
        "_model_trace": [],
        "_model_usage": [],
    }


def _play(turn: dict, player_input: str, model: Model | None = None):
    model = model or Model()
    with mock.patch.object(world, "generate_turn", side_effect=lambda *a, **k: turn), mock.patch.object(
        llm, "_chat_content", side_effect=model
    ):
        return world.play_turn(player_input)


def _context(line: str) -> dict:
    return world.build_prompt_context(world.get_state(), line)


def _attack_people(line: str) -> tuple[dict | None, dict]:
    def ask(phase: str, prompt: str, max_tokens: int) -> str:
        return "Yes" if phase == attack_intent.PHASE_ATTACK else "No"

    return attack_intent.decide(line, _context(line), None, ask)


class FinalReplayNateIsWhereThePlayerMetHim(unittest.TestCase):
    """live/final T1 then T3."""

    def setUp(self):
        self.town = _fresh_world()
        self.clinic, self.clinic_code = _add_place(CLINIC, parent_id=self.town, kind="clinic")
        # The opening pencilled Nate in at the town (sketch_turn 1), as the run did.
        self.nate = _add_npc("Nate", self.town, role="field tech", sketch_turn=1)
        self.t1 = FINAL_T1.replace("[[A]]", f"[[{self.nate}]]")

    def test_t1_nate_at_his_workbench_is_filed_in_the_clinic(self):
        model = Model({"Nate": "Yes, Nate says something"})
        _play(_turn(self.t1, move_to=CLINIC), FINAL_T1_LINE, model)
        self.assertEqual(_here_id(), self.clinic)
        self.assertTrue(model.asked_about("Nate"))
        self.assertEqual(_place_of(self.nate), self.clinic)

    def test_t3_the_attack_ask_finds_nate_here(self):
        _play(_turn(self.t1, move_to=CLINIC), FINAL_T1_LINE, Model({"Nate": "Yes, Nate says something"}))
        check, report = _attack_people(FINAL_T3_LINE)
        self.assertIn(self.nate, report.get("people") or [])
        self.assertEqual(attack_intent.attack_target(check), self.nate)

    def test_a_no_leaves_him_where_the_records_have_him(self):
        """Reverse: the ask's no moves nobody (no answer, no action)."""
        _play(_turn(self.t1, move_to=CLINIC), FINAL_T1_LINE, Model({"Nate": "No"}))
        self.assertEqual(_place_of(self.nate), self.town)

    def test_the_narrator_is_told_where_the_player_is(self):
        before = prompts._visible_world(_context(FINAL_T1_LINE), FINAL_T1_LINE)["current_location"]
        self.assertEqual(next(iter(before)), "player_is_in")
        self.assertEqual(before["player_is_in"], f"{TOWN} [[L{self.town}]].")
        _play(_turn(self.t1, move_to=CLINIC), FINAL_T1_LINE, Model({"Nate": "Yes"}))
        after = prompts._visible_world(_context(FINAL_T3_LINE), FINAL_T3_LINE)["current_location"]
        self.assertEqual(next(iter(after)), "player_is_in")
        self.assertEqual(after["player_is_in"], f"{CLINIC} [[{self.clinic_code}]], inside {TOWN} [[L{self.town}]].")
        # And Nate is one of the people there.
        self.assertIn(self.nate, [p.get("code") for p in after.get("people") or []])

    def test_rewind_takes_nate_back_to_the_town(self):
        _play(_turn(self.t1, move_to=CLINIC), FINAL_T1_LINE, Model({"Nate": "Yes"}))
        self.assertEqual(_place_of(self.nate), self.clinic)
        world.rewind_last_turn()
        self.assertEqual(_place_of(self.nate), self.town)
        self.assertEqual(_here_id(), self.town)


class APersonTheTurnIntroducesIsFiledHere(unittest.TestCase):
    def setUp(self):
        self.town = _fresh_world()
        self.clinic, self.clinic_code = _add_place(CLINIC, parent_id=self.town, kind="clinic")

    def test_integ_r4_t1_vasilis_is_seeded_in_the_clinic(self):
        _play(_turn(R4_T1, move_to=CLINIC), FINAL_T1_LINE)
        self.assertEqual(_here_id(), self.clinic)
        self.assertEqual(_place_of_name("Vasilis"), self.clinic)

    def test_an_npc_op_written_before_the_move_is_filed_after_it(self):
        """The ops run before the player's move: NPC_NEW Nate with no LOC landed in the town."""
        prose = FINAL_T1.replace(" [[A]]", "")
        npcs = [{"code": "A", "name": "Nate", "role": "field tech", "location": ""}]
        _play(_turn(prose, move_to=CLINIC, npcs=npcs), FINAL_T1_LINE)
        self.assertEqual(_here_id(), self.clinic)
        self.assertEqual(_place_of_name("Nate"), self.clinic)

    def test_an_op_loc_the_prose_shows_them_at_is_kept(self):
        """Reverse: LOC names another known place and the prose shows them there."""
        hall, hall_code = _add_place("Town Hall", parent_id=self.town)
        prose = (
            "You stay by the clinic door. Through the window you see Aldric Vane crossing to the Town Hall "
            f"[[{hall_code}]] with a sheaf of papers."
        )
        npcs = [{"code": "", "name": "Aldric Vane", "role": "mayor", "location": "Town Hall"}]
        with db.connect().closing() as conn:
            conn.execute("UPDATE player SET current_location_id = ?", (self.clinic,))
            conn.commit()
        _play(_turn(prose, npcs=npcs), "I look out of the window.")
        self.assertEqual(_place_of_name("Aldric Vane"), hall)


class SomeoneNamedAsElsewhereStaysElsewhere(unittest.TestCase):
    def setUp(self):
        self.town = _fresh_world()
        self.clinic, self.clinic_code = _add_place(CLINIC, parent_id=self.town, kind="clinic")
        self.hall, self.hall_code = _add_place("Town Hall", parent_id=self.town)
        with db.connect().closing() as conn:
            conn.execute("UPDATE player SET current_location_id = ?", (self.clinic,))
            conn.commit()
        self.kim = _add_npc("Kim", self.clinic, role="cleaner")
        self.mayor = _add_npc("Aldric Vane", self.hall, role="mayor")

    def test_the_mayor_is_at_the_town_hall_said_by_kim(self):
        prose = (
            f"Kim [[{self.kim}]] leans on her mop. \"The mayor? Aldric Vane is at the Town Hall most days,\" she says."
        )
        model = Model({"Aldric Vane": "Yes"})
        _play(_turn(prose), "where is the mayor?", model)
        self.assertFalse(model.asked_about("Aldric Vane"))  # only spoken of: not asked
        self.assertEqual(_place_of(self.mayor), self.hall)

    def test_the_mayor_is_at_the_town_hall_in_the_narration(self):
        """Told, not quoted; even a yes keeps him where the sentence puts him."""
        prose = f"Kim [[{self.kim}]] tells you the mayor, Aldric Vane, is at the Town Hall [[{self.hall_code}]] today."
        _play(_turn(prose), "where is the mayor?", Model({"Aldric Vane": "Yes"}))
        self.assertEqual(_place_of(self.mayor), self.hall)

    def test_a_name_heard_of_at_a_place_never_seen_is_not_filed_with_the_player(self):
        """8B run 150, T92 (tests/test_places_have_insides.py): someone only heard of stays in the town."""
        prose = (
            "The words were smudged, but you could make out the name Veyra at the bottom. A name you'd heard "
            f"whispered in the Smugglers' Den. Kim [[{self.kim}]]'s gaze followed yours."
        )
        npcs = [{"name": "Veyra", "role": "mysterious figure", "location": "the Smugglers' Den"}]
        _play(_turn(prose, npcs=npcs), "I hold out my hand.")
        self.assertEqual(_place_of_name("Veyra"), self.town)

    def test_the_mayor_walking_in_is_here(self):
        """The other way round: shown with the player, he is here."""
        prose = f"The door bangs open. Aldric Vane strides in and nods at Kim [[{self.kim}]]. \"Busy morning,\" he says."
        _play(_turn(prose), "I wait.", Model({"Aldric Vane": "Yes, he says something"}))
        self.assertEqual(_place_of(self.mayor), self.clinic)

    def test_someone_left_behind_when_the_player_leaves(self):
        """Named only before the player leaves: the yes does not carry him along."""
        prose = (
            f"You thank Aldric Vane for his time and step out of the Town Hall [[{self.hall_code}]] into the morning. "
            "The street is quiet."
        )
        with db.connect().closing() as conn:
            conn.execute("UPDATE player SET current_location_id = ?", (self.hall,))
            conn.commit()
        street, _street_code = _add_place("Low Street", parent_id=self.town)
        _play(_turn(prose, move_to="Low Street"), "I leave the town hall.", Model({"Aldric Vane": "Yes"}))
        self.assertEqual(_here_id(), street)
        self.assertEqual(_place_of(self.mayor), self.hall)


class TheDecisionIsOneHelper(unittest.TestCase):
    """whereabouts.decide on its own, with the records only (no ask)."""

    def setUp(self):
        self.town = _fresh_world()
        self.clinic, self.clinic_code = _add_place(CLINIC, parent_id=self.town, kind="clinic")
        self.nate = _add_npc("Nate", self.town, role="field tech")

    def _decide(self, text: str, here_at_start: int = 0) -> tuple[int, str]:
        with db.connect().closing() as conn:
            npc_id = int(conn.execute("SELECT id FROM npcs WHERE code = ?", (self.nate,)).fetchone()[0])
            return whereabouts.decide(conn, npc_id, text, here=self.clinic, here_at_start=here_at_start)

    def test_shown_in_the_clinic_is_here(self):
        self.assertEqual(self._decide(FINAL_T1.replace("[[A]]", f"[[{self.nate}]]"), self.town), (self.clinic, "filed_here"))

    def test_the_town_around_the_clinic_is_not_elsewhere(self):
        text = f"Nate [[{self.nate}]], the best tech in {TOWN} [[L{self.town}]], looks up from his bench."
        self.assertEqual(self._decide(text), (self.clinic, "filed_here"))

    def test_the_town_the_player_just_left_is_elsewhere(self):
        text = (
            f"Nate [[{self.nate}]] waves from the {TOWN} [[L{self.town}]] gate as you step into the clinic. "
            "The cots are empty."
        )
        self.assertEqual(self._decide(text, self.town), (self.town, "shown_elsewhere"))

    def test_the_dead_are_not_moved(self):
        with db.connect().closing() as conn:
            conn.execute("UPDATE npcs SET died_turn = 1 WHERE code = ?", (self.nate,))
            conn.commit()
        self.assertEqual(self._decide(FINAL_T1.replace("[[A]]", f"[[{self.nate}]]"))[1], "dead")


class TheInterpreterAsksOnlyAboutPeopleElsewhere(unittest.TestCase):
    def _records(self, here_id: int = 2) -> dict:
        return {
            "people": [
                {"code": "A", "name": "Nate", "died_turn": 0, "location_id": 1},
                {"code": "B", "name": "Kim", "died_turn": 0, "location_id": 2},
                {"code": "C", "name": "Beth", "died_turn": 3, "location_id": 1},
            ],
            "places": [{"code": "L1", "name": TOWN}, {"code": "L2", "name": CLINIC}],
            "here_id": here_id,
        }

    def _run(self, text: str, events: list | None = None) -> tuple[list[str], list[str]]:
        asked: list[str] = []

        def ask(phase: str, prompt: str, max_tokens: int) -> str:
            asked.append(prompt)
            return "Yes"

        report = {"asks": [], "held": [], "events": [], "unconfirmed": []}
        return I.with_player(text, events or [], self._records(), ask, report), asked

    def test_someone_elsewhere_shown_acting_is_asked_about(self):
        codes, asked = self._run(FINAL_T1)
        self.assertEqual(codes, ["A"])
        self.assertEqual(len(asked), 1)
        self.assertIn("Does Nate say or do anything in it?", asked[0])

    def test_nobody_here_or_dead_or_only_spoken_of_is_asked_about(self):
        text = f'Kim [[B]] sweeps. Beth [[C]] lies still. "Nate went to the {TOWN}," Kim says.'
        codes, asked = self._run(text)
        self.assertEqual((codes, asked), ([], []))

    def test_someone_who_died_this_turn_is_the_body_asks(self):
        died = [{"kind": I.KIND_DIED, "subject": {"type": "npc", "code": "A", "name": "Nate"}}]
        codes, asked = self._run(FINAL_T1, died)
        self.assertEqual((codes, asked), ([], []))


if __name__ == "__main__":
    unittest.main()
