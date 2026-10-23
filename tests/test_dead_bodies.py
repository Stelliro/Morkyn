"""The dead leave a body (CLAUDE.md, Design decisions, 2026-10-24).

"we shouldnt just remove dead npcs, as they should not just vanish, they
should have a dead body". A dead person stays where they died as a body: in
the place's records and the next scene's context as dead and present, never
as someone who talks or acts; the body can be searched, moved or buried.

The strings are the tester's Hermes 3 8B game (campaign cc87dd29: T10 Beth
ripped in half, T11 "i search Beth's body" and she speaks) and the final
replay of 2026-10-24 (live/final: T3 "i shoot Nate" with the roster placing
him in the town while the player stood in the clinic, T4 "rip him in half",
T5 "i search Nate's body"). The model is mocked; the hold's replies are the
ones Hermes 3 8B gave (docs/showcase/ask-live-eval-2026-10-24.md). The body
asks are new and not measured: their mocked replies are what a right answer
would be.

Run:  cd tests && python -m unittest test_dead_bodies
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-bodies-test-"))
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

from app import db, interpreter, llm, prompts, world  # noqa: E402
from app.turn_dsl import facts_to_keep  # noqa: E402

I = interpreter

# --- cc87dd29 T10: "i walk up to @Cbeth and ... rip her in half" ------------
T10_LINE = (
    "i walk up to @Cbeth and grab her arms with one hand and her legs with the other, and i rip her in half, "
    "this move grants her instant death"
)
T10 = (
    "You lunge towards Beth [[B]], grabbing her arms with one hand and her legs with the other. With a violent twist, "
    "you attempt to rip her in two, your muscles straining against her flesh.\n\n"
    "Morning light filters in through grimy windows, casting an eerie pallor over the clinic's cold stone floors. The air "
    "is thick with the stench of decay and the sound of your own heavy breathing. Beth [[B]] screams in agony as you "
    "wrench her arms and legs with a savage grip. She thrashes and struggles, trying to break free from your iron hold.\n\n"
    "A sickening tear rips through her flesh as you wrench her body apart. Gore and viscera splatter across the floor in "
    "a grisly display. Her entrails spill out across the hard stone, pooling in a dark crimson puddle as her lifeless "
    "upper body collapses to the ground. You stand over the grisly remains, your arms and torso splattered in Beth "
    "[[B]]'s blood and innards.\n\n"
    "The clinic falls silent, save for the sound of your heart pounding in your ears. The life has been ripped from her, "
    "leaving only a macabre still life behind. Beth [[B]]'s wide, dead eyes stare up at the stained ceiling, her body "
    "split down the middle in an act of savage violence. You stand over her corpse, the fruits of your brutality "
    "staining your hands and chest with her blood and gore."
)
# --- cc87dd29 T11: "i search Beth's body" and she speaks --------------------
T11_LINE = "i search Beth's body"
T11 = (
    "You pat Beth [[B]] down carefully, searching for any hidden weapons or items. The doctor's coat she wears is thick, "
    "but you feel around every pocket and seam. To your surprise, she is not carrying anything - no knife, gun, or even "
    "a small pouch. Beth [[B]] frowns, clearly puzzled by your actions. \"You're looking for something? I don't have "
    "anything to give or sell. Now state your business, or leave.\" Her words are firm, with an edge of warning in her "
    "voice.\n\n"
    "The clinic looks old and ramshackle but functional. Beth [[B]], a middle-aged woman in a doctor's coat, steps out "
    "from the clinic. She regards you with suspicion. \"State your business here,\" she says."
)
# Hermes 3 8B's replies to the per-sentence hold ask on T11 (live eval).
T11_WHICH = {
    "You pat Beth down": 'No, in the sentence "You pat',
    "The doctor's coat": "No, Beth does not say or do",
    "To your surprise": "No, Beth does not say or do",
    "Beth frowns": "No.",
    "\"You're looking for something?": "Yes, Beth says something in the sentence",
    "Her words are firm": "No.",
    "The clinic looks old": "No, Beth does not say or do",
    "Beth, a middle-aged woman": 'No. In the sentence "Beth,',
    "She regards you": 'Yes, in the sentence "She regards',
    "\"State your business here,\"": "Yes, Beth says something in the sentence",
}

# --- live/final (2026-10-24): Nate in the town on record, the player in the clinic
FINAL_T3_LINE = "i shoot Nate"
FINAL_T3 = (
    "You crouch behind a rusted air scrubber, aiming your X-01 at Nate [[A]]'s heart. Morning light glints off the "
    "energy bolt as you squeeze the trigger. It streaks across the gap between the two scaffold towns, striking Nate "
    "[[A]] square in the chest. His eyes widen in shock, and he staggers back two steps before collapsing face-first "
    "onto the gravel.\n\n"
    "Nate [[A]] lies motionless, his body sprawled in the dirt. You approach cautiously, wary of a final surprise, but "
    "he remains still and lifeless. You kick his field tech tools out of reach, not wanting him to have anything that "
    "might help his allies. Satisfied that he's dead, you turn and walk back to the Radiation Fenced Sanctuary Clinic "
    "[[L2]], leaving Nate [[A]]'s body where it fell in the pale morning light."
)
FINAL_T4_LINE = (
    "i walk up to Nate and grab his arms with one hand and his legs with the other, and i rip him in half, "
    "this move grants him instant death"
)
FINAL_T4 = (
    "You stride up to Nate [[A]], grab his arms with one hand and his legs with the other, and rip him in half with a "
    "sudden twist. The brutal violence leaves no doubt - Nate [[A]] is dead, his body split cleanly in two. Blood and "
    "gore splatter the ground around you."
)
FINAL_T5_LINE = "i search Nate's body"
FINAL_T5 = (
    "You search the body of the man you killed, looking for anything useful that might have been on him. The X-01 is "
    "your only source of illumination, casting a cold blue glow over the scene. It's early in the day and the air is "
    "fresh but cool. The ground under your boots is hard-packed dirt. The clinic around you is mostly deserted at this "
    "hour."
)

# Not from a run (nobody has buried or carried a body in a recorded game yet).
BURIAL = (
    "You dig a shallow grave behind the clinic and lay Beth [[B]] in it. You shovel the earth back over her until the "
    "grave is level with the yard, and set a flat stone on top."
)
CARRY = (
    "You heave Beth [[B]] over your shoulder. Her weight settles against your armor as you turn toward the door, "
    "carrying her out of the clinic."
)


def _sentence_of(prompt: str) -> str:
    found = re.search(r'In the sentence "(.*)", does ', prompt, re.S)
    return found.group(1) if found else ""


# Which ask a prompt is (the transport is not told the phase). Body asks first:
# "Is Beth's body buried at the end of it?" must not read as a death ask.
_MARKERS = (
    ("'s body with the player", I.PHASE_BODY_HERE),
    ("walked away from", I.PHASE_BODY_HERE_CHECK),
    ("'s body in a grave", I.PHASE_BODY_BURIED),
    ("'s body be seen", I.PHASE_BODY_BURIED_CHECK),
    ("in the player's arms", I.PHASE_BODY_CARRIED),
    ("'s body lying on the ground", I.PHASE_BODY_CARRIED_CHECK),
    ("still dead at the end", I.PHASE_RETURNED_CHECK),
    ("dead at the end", I.PHASE_DIED),
    ("alive at the end", I.PHASE_DIED_CHECK),
    ("destroyed at the end", I.PHASE_DESTROYED),
    ("still standing at the end", I.PHASE_DESTROYED_CHECK),
    ("say or do anything in it", I.PHASE_HOLD),
    ("come back from death", I.PHASE_RETURNED),
    ("In the sentence", I.PHASE_WHICH),
)


def _phase_of(prompt: str) -> str:
    for marker, phase in _MARKERS:
        if marker in prompt:
            return phase
    return ""


class Model:
    """Replies by phase ("No" unless given); ``which``: sentence start -> reply."""

    def __init__(self, replies: dict[str, str] | None = None, which: dict[str, str] | None = None):
        self.replies = dict(replies or {})
        self.which = dict(which or {})
        self.calls: list[tuple[str, str]] = []

    def __call__(self, phase: str, prompt: str, max_tokens: int) -> str:
        self.calls.append((phase, prompt))
        if phase == I.PHASE_WHICH:
            sentence = _sentence_of(prompt)
            for start, reply in self.which.items():
                if sentence.startswith(start):
                    return reply
            return "No."
        return self.replies.get(phase, "No")

    def phases(self) -> list[str]:
        return [p for p, _ in self.calls]


DIES = {I.PHASE_DIED: "Yes, she is dead at the end", I.PHASE_DIED_CHECK: "No, she is not alive"}


def _fresh_world():
    os.environ.update(_ENV)
    assert str(db.db_path()).startswith(str(_TMP)), db.db_path()
    db.init_db()
    world.start_playthrough({"player_name": "Ash", "start_location": "Low Gate", "special_ability_origin": "none"})


def _here_id() -> int:
    with db.connect().closing() as conn:
        return int(conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()["current_location_id"])


def _add_place(name: str, parent_id: int = 0, kind: str = "") -> tuple[int, str]:
    with db.connect().closing() as conn:
        code = world._next_location_code(conn) if hasattr(world, "_next_location_code") else None
        if not code:
            n = conn.execute("SELECT COUNT(*) AS n FROM locations").fetchone()["n"]
            code = f"L{int(n) + 1}"
        cur = conn.execute(
            "INSERT INTO locations (code, name, summary, visit_count, parent_id, kind) VALUES (?, ?, '', 0, ?, ?)",
            (code, name, int(parent_id), kind),
        )
        conn.commit()
        return int(cur.lastrowid), code


def _add_npc(name: str, location_id: int | None = None, died_turn: int = 0) -> str:
    with db.connect().closing() as conn:
        loc = location_id or conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()["current_location_id"]
        code = world._next_alpha_code(conn, "npcs")
        conn.execute("INSERT INTO npcs (code, location_id, name, died_turn) VALUES (?, ?, ?, ?)", (code, int(loc), name, died_turn))
        conn.commit()
        return code


def _row(code: str) -> dict:
    with db.connect().closing() as conn:
        row = conn.execute("SELECT * FROM npcs WHERE code = ?", (code,)).fetchone()
        return {k: row[k] for k in row.keys()}


def _turn(narration: str, pending: bool = True) -> dict:
    turn = {
        "scene_plan": {"goal": "look", "focus_points": []},
        "narration_segments": [{"label": "scene", "text": narration}],
        "narration": narration,
        "player": {},
        "self_check": {"passed": True, "issues_found": [], "corrections_made": []},
        "turn_summary": "a beat",
        "scene_focus": "action",
        "scene_cast": {"present": [], "interacting": [], "off": []},
    }
    if pending:
        turn["_interpreter_pending"] = {"config": {}}
        turn["_model_trace"] = []
        turn["_model_usage"] = []
    return turn


def _play(turn: dict, player_input: str, model: Model | None = None, seen: dict | None = None):
    def content(system, user, **kwargs):
        phase = _phase_of(user)
        return model(phase, user, kwargs.get("max_tokens") or 8) if model and phase else "No"

    def gen(context, line, *args, **kwargs):
        if seen is not None:
            seen["context"] = context
        return turn

    with mock.patch.object(world, "generate_turn", side_effect=gen), mock.patch.object(llm, "_chat_content", side_effect=content):
        return world.play_turn(player_input)


def _shipped() -> str:
    files = sorted((_TMP / "traces").glob("turn-*.json"), key=lambda p: p.stat().st_mtime)
    return json.loads(files[-1].read_text(encoding="utf-8"))["final_turn"]["narration"]


def _context(line: str) -> dict:
    return world.build_prompt_context(world.get_state(), line)


class TestTesterT10T11TheBodyIsThere(unittest.TestCase):
    """cc87dd29 T10 -> T11: Beth killed, then her body searched; she stays a body and does not speak."""

    def setUp(self):
        _fresh_world()
        self.code = _add_npc("Beth")
        self.living = _add_npc("Kim")
        self.t10 = T10.replace("[[B]]", f"[[{self.code}]]")
        self.t11 = T11.replace("[[B]]", f"[[{self.code}]]")

    def test_t10_then_t11(self):
        here = _here_id()
        _play(_turn(self.t10), T10_LINE.replace("@C", f"@{self.code}"), Model(DIES))
        row = _row(self.code)
        self.assertGreater(int(row["died_turn"]), 0)
        self.assertEqual(int(row["location_id"]), here)  # the body is where she died
        died = int(row["died_turn"])

        # The next turn's context: dead and present as a body, not a person here.
        context = _context(T11_LINE)
        bodies = (context.get("current_location") or {}).get("bodies") or []
        self.assertEqual([(b["code"], b["body"], b["died_turn"]) for b in bodies], [(self.code, "lies", died)])
        kept = facts_to_keep(context)
        self.assertIn(f"Beth [[{self.code}]] died in turn {died} and is dead.", kept)
        self.assertIn(f"The body of Beth [[{self.code}]] lies here.", kept)
        for location in context.get("locations") or []:
            self.assertNotIn(self.code, [n.get("code") for n in location.get("npcs") or []])
        # The narrator's view of the place: the body, and the living as people.
        view = prompts._visible_world(context, T11_LINE).get("current_location") or {}
        self.assertEqual([b["code"] for b in view.get("bodies") or []], [self.code])
        self.assertNotIn(self.code, [p.get("code") for p in view.get("people") or []])
        # Reverse: the living person at the place is a person, not a body.
        self.assertIn(self.living, [p.get("code") for p in view.get("people") or []])
        self.assertNotIn(self.living, [b["code"] for b in bodies])

        # T11: the hold cuts her speech; the body asks are asked (the line names
        # her) and say nothing changed; the body stays.
        seen: dict = {}
        model = Model({I.PHASE_HOLD: "Yes, she says something in the text"}, which=T11_WHICH)
        _play(_turn(self.t11), T11_LINE, model, seen)
        shipped = _shipped()
        self.assertIn(f"You pat Beth [[{self.code}]] down carefully", shipped)
        self.assertNotIn("State your business here", shipped)
        self.assertNotIn("You're looking for something?", shipped)
        self.assertIn(I.PHASE_BODY_BURIED, model.phases())
        self.assertIn(I.PHASE_BODY_CARRIED, model.phases())
        talk = seen["context"].get("conversation_turn") or {}
        self.assertNotIn(self.code, talk.get("addressed") or [])
        self.assertNotIn(self.code, talk.get("present") or [])
        self.assertEqual([b["code"] for b in (seen["context"].get("current_location") or {}).get("bodies") or []], [self.code])
        row = _row(self.code)
        self.assertEqual((int(row["died_turn"]), int(row["location_id"]), row["body"]), (died, here, ""))

    def test_state_keeps_the_dead_in_the_place_for_the_ui(self):
        _play(_turn(self.t10), T10_LINE, Model(DIES))
        state = world.get_state()
        here = next(loc for loc in state["locations"] if loc["id"] == _here_id())
        beth = next(n for n in here["npcs"] if n["code"] == self.code)
        self.assertGreater(int(beth["died_turn"]), 0)
        self.assertEqual(beth["body"], "")

    def test_no_body_ask_when_the_line_does_not_name_her(self):
        _play(_turn(self.t10), T10_LINE, Model(DIES))
        model = Model()
        _play(_turn(self.t11), "I look around", model)
        self.assertNotIn(I.PHASE_BODY_BURIED, model.phases())
        self.assertNotIn(I.PHASE_BODY_CARRIED, model.phases())


class TestFinalReplayTheBodyWhereTheProseLeavesIt(unittest.TestCase):
    """live/final T3-T5: the roster had Nate in the town while the player stood in the clinic."""

    def setUp(self):
        _fresh_world()
        self.clinic = _here_id()
        self.town, self.town_code = _add_place("Radiation Fenced Sanctuary")
        self.code = _add_npc("Nate", location_id=self.town)

    def _text(self, text: str) -> str:
        return text.replace("[[A]]", f"[[{self.code}]]")

    def test_t3_left_where_it_fell_stays_at_the_record(self):
        model = Model({**DIES, I.PHASE_BODY_HERE: "No", I.PHASE_BODY_HERE_CHECK: "Yes"})
        _play(_turn(self._text(FINAL_T3)), FINAL_T3_LINE, model)
        row = _row(self.code)
        self.assertGreater(int(row["died_turn"]), 0)
        self.assertIn(I.PHASE_BODY_HERE, model.phases())
        self.assertEqual(int(row["location_id"]), self.town)
        context = _context(FINAL_T5_LINE)
        self.assertFalse((context.get("current_location") or {}).get("bodies"))
        self.assertNotIn(f"The body of Nate [[{self.code}]] lies here.", facts_to_keep(context))
        town = next((loc for loc in context.get("locations") or [] if loc.get("id") == self.town), None)
        if town is not None:  # the town is in the slice: its body is listed there
            self.assertEqual([b["code"] for b in town.get("bodies") or []], [self.code])

    def test_t4_with_the_player_moves_here_then_t5_searches_it(self):
        model = Model({**DIES, I.PHASE_BODY_HERE: "Yes, his body is with the player", I.PHASE_BODY_HERE_CHECK: "No"})
        _play(_turn(self._text(FINAL_T4)), FINAL_T4_LINE, model)
        self.assertEqual([p for p in model.phases() if p.startswith("interpreter_body_here")],
                         [I.PHASE_BODY_HERE, I.PHASE_BODY_HERE_CHECK])
        row = _row(self.code)
        self.assertGreater(int(row["died_turn"]), 0)
        self.assertEqual(int(row["location_id"]), self.clinic)
        # T5: "i search Nate's body": the body is in the context; the prose does
        # not name him, so nothing is asked about him and nothing changes.
        seen: dict = {}
        model5 = Model()
        _play(_turn(FINAL_T5), FINAL_T5_LINE, model5, seen)
        bodies = (seen["context"].get("current_location") or {}).get("bodies") or []
        self.assertEqual([b["code"] for b in bodies], [self.code])
        self.assertIn(f"The body of Nate [[{self.code}]] lies here.", facts_to_keep(seen["context"]))
        self.assertNotIn(I.PHASE_HOLD, model5.phases())
        self.assertEqual(int(_row(self.code)["location_id"]), self.clinic)

    def test_same_place_asks_nothing_about_the_place(self):
        with db.connect().closing() as conn:
            conn.execute("UPDATE npcs SET location_id = ? WHERE code = ?", (self.clinic, self.code))
            conn.commit()
        model = Model(DIES)
        _play(_turn(self._text(FINAL_T4)), FINAL_T4_LINE, model)
        self.assertNotIn(I.PHASE_BODY_HERE, model.phases())
        self.assertEqual(int(_row(self.code)["location_id"]), self.clinic)

    def test_an_npc_op_does_not_move_a_body(self):
        _play(_turn(self._text(FINAL_T3)), FINAL_T3_LINE, Model(DIES))
        with db.connect().closing() as conn:
            world._upsert_npc(conn, {"code": self.code, "name": "Nate", "location": "Low Gate", "role": "dead man"})
            conn.commit()
        self.assertEqual(int(_row(self.code)["location_id"]), self.town)


class TestAKeeperWhoDies(unittest.TestCase):
    def setUp(self):
        _fresh_world()
        town = _here_id()
        self.clinic, self.clinic_code = _add_place("Radiation Fenced Sanctuary Clinic", parent_id=town, kind="clinic")
        self.code = _add_npc("Beth", location_id=self.clinic)
        with db.connect().closing() as conn:
            npc_id = conn.execute("SELECT id FROM npcs WHERE code = ?", (self.code,)).fetchone()["id"]
            conn.execute("UPDATE locations SET keeper_npc_id = ? WHERE id = ?", (int(npc_id), self.clinic))
            conn.execute("UPDATE npcs SET workplace_id = ?, role = 'doctor' WHERE code = ?", (self.clinic, self.code))
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (self.clinic,))
            conn.commit()

    def test_alive_she_keeps_the_place(self):
        state = world.get_state()
        self.assertEqual((state["current_location"].get("keeper") or {}).get("code"), self.code)
        context = _context("i buy some bandages from Beth")
        self.assertEqual((context["current_location"].get("keeper") or {}).get("code"), self.code)
        self.assertFalse(context["current_location"].get("bodies"))

    def test_dead_the_place_has_no_keeper_and_her_body(self):
        with db.connect().closing() as conn:
            conn.execute("UPDATE npcs SET died_turn = 3 WHERE code = ?", (self.code,))
            conn.commit()
        state = world.get_state()
        self.assertNotIn("keeper", state["current_location"])
        clinic = next(loc for loc in state["locations"] if loc["id"] == self.clinic)
        self.assertIn(self.code, [n["code"] for n in clinic["npcs"]])  # the record keeps her there
        context = _context("i buy some bandages from Beth")
        self.assertNotIn("keeper", context["current_location"])
        self.assertEqual([b["code"] for b in context["current_location"].get("bodies") or []], [self.code])
        view = prompts._visible_world(context, "i buy some bandages from Beth").get("current_location") or {}
        self.assertNotIn("keeper", view)
        self.assertEqual([b["code"] for b in view.get("bodies") or []], [self.code])
        # The keeper pointer stays (rewind, and the clinic's history).
        with db.connect().closing() as conn:
            self.assertTrue(int(conn.execute("SELECT keeper_npc_id FROM locations WHERE id = ?", (self.clinic,)).fetchone()[0]))


class TestBuriedCarriedAndRewind(unittest.TestCase):
    def setUp(self):
        _fresh_world()
        _play(_turn("The yard is quiet. " * 20, pending=False), "I look around")
        self.here = _here_id()
        self.code = _add_npc("Beth")
        self.t10 = T10.replace("[[B]]", f"[[{self.code}]]")
        _play(_turn(self.t10), T10_LINE, Model(DIES))
        self.assertGreater(int(_row(self.code)["died_turn"]), 0)

    def test_buried_after_the_check(self):
        model = Model({I.PHASE_BODY_BURIED: "Yes, her body is buried", I.PHASE_BODY_BURIED_CHECK: "No"})
        _play(_turn(BURIAL.replace("[[B]]", f"[[{self.code}]]")), "i bury Beth behind the clinic", model)
        self.assertEqual(_row(self.code)["body"], "buried")
        self.assertNotIn(I.PHASE_BODY_CARRIED, model.phases())
        context = _context("I look around")
        self.assertIn(f"Beth [[{self.code}]] is buried here.", facts_to_keep(context))
        self.assertEqual([b["body"] for b in context["current_location"]["bodies"]], ["buried"])

    def test_a_burial_the_check_does_not_confirm_is_not_recorded(self):
        model = Model({I.PHASE_BODY_BURIED: "Yes", I.PHASE_BODY_BURIED_CHECK: "Yes, it can be seen"})
        _play(_turn(BURIAL.replace("[[B]]", f"[[{self.code}]]")), "i bury Beth behind the clinic", model)
        self.assertEqual(_row(self.code)["body"], "")

    def test_carried_follows_the_player_then_set_down(self):
        model = Model({I.PHASE_BODY_CARRIED: "Yes", I.PHASE_BODY_CARRIED_CHECK: "No"})
        _play(_turn(CARRY.replace("[[B]]", f"[[{self.code}]]")), "i carry Beth's body outside", model)
        self.assertEqual(_row(self.code)["body"], "carried")
        other, _code = _add_place("Thornford")
        with db.connect().closing() as conn:
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (other,))
            conn.commit()
        _play(_turn("The road is long and empty. " * 12, pending=False), "I walk on")
        self.assertEqual(int(_row(self.code)["location_id"]), other)
        self.assertIn(f"You carry the body of Beth [[{self.code}]].", facts_to_keep(_context("I look around")))
        # Set down: the line names her and the carry ask says no.
        put = f"You lower Beth [[{self.code}]] to the ground by the road and straighten your back."
        _play(_turn(put), "i put Beth's body down", Model())
        row = _row(self.code)
        self.assertEqual((row["body"], int(row["location_id"])), ("", other))

    def test_rewind_brings_her_back_alive_and_standing(self):
        model = Model({I.PHASE_BODY_CARRIED: "Yes", I.PHASE_BODY_CARRIED_CHECK: "No"})
        _play(_turn(CARRY.replace("[[B]]", f"[[{self.code}]]")), "i carry Beth's body outside", model)
        self.assertEqual(_row(self.code)["body"], "carried")
        world.rewind_last_turn()
        row = _row(self.code)
        self.assertEqual(row["body"], "")
        self.assertGreater(int(row["died_turn"]), 0)
        world.rewind_last_turn()
        row = _row(self.code)
        self.assertEqual((int(row["died_turn"]), row["body"], int(row["location_id"])), (0, "", self.here))
        context = _context("i say hi to Beth")
        self.assertFalse((context.get("current_location") or {}).get("bodies"))
        self.assertIn(self.code, [n.get("code") for loc in context.get("locations") or [] for n in loc.get("npcs") or []])

    def test_returned_clears_the_body(self):
        with db.connect().closing() as conn:
            conn.execute("UPDATE npcs SET body = 'carried' WHERE code = ?", (self.code,))
            I.apply_events(conn, 9, [I._event(I.KIND_RETURNED, "npc", {"code": self.code, "name": "Beth"}, "she rises")])
            conn.commit()
        row = _row(self.code)
        self.assertEqual((int(row["died_turn"]), row["body"]), (0, ""))


class TestTheEventShape(unittest.TestCase):
    def setUp(self):
        _fresh_world()
        self.code = _add_npc("Beth", died_turn=4)
        self.alive = _add_npc("Kim")

    def test_a_body_event_for_the_living_is_refused(self):
        with db.connect().closing() as conn:
            out = I.apply_events(conn, 5, [{**I._event(I.KIND_BODY, "npc", {"code": self.alive, "name": "Kim"}, ""), "state": "buried"}])
        self.assertEqual((out[0]["status"], out[0]["reason"]), ("refused", "not dead"))

    def test_an_unknown_body_state_is_refused(self):
        with db.connect().closing() as conn:
            out = I.apply_events(conn, 5, [{**I._event(I.KIND_BODY, "npc", {"code": self.code, "name": "Beth"}, ""), "state": "eaten"}])
        self.assertEqual(out[0]["reason"], "unknown body state")

    def test_the_summary_line_of_a_burial(self):
        event = {**I._event(I.KIND_BODY, "npc", {"code": self.code, "name": "Beth"}, ""), "state": "buried"}
        self.assertEqual(I.event_line(event), f"Beth [[{self.code}]] was buried.")

    def test_read_bodies_asks_nothing_for_a_body_elsewhere(self):
        records = {"people": [{"code": "B", "name": "Beth", "died_turn": 4, "location_id": 7, "body": "lies"}],
                   "places": [], "here_id": 3, "player_line": T11_LINE}
        model = Model()
        self.assertEqual(I.read_bodies(T11, records, model, {"asks": [], "unconfirmed": []}), [])
        self.assertEqual(model.calls, [])

    def test_an_old_save_without_the_body_column(self):
        with db.connect().closing() as conn:
            conn.execute("ALTER TABLE npcs DROP COLUMN body")
            conn.commit()
            records = I.load_records(conn)
            self.assertIn(self.code, [p["code"] for p in records["people"]])
            self.assertEqual(I.carry_bodies(conn, 5), [])
        db.init_db()
        with db.connect().closing() as conn:
            self.assertIn("body", [r[1] for r in conn.execute("PRAGMA table_info(npcs)").fetchall()])
        context = _context("I look around")
        self.assertIn(f"The body of Beth [[{self.code}]] lies here.", facts_to_keep(context))


class TestTheUiShowsTheBody(unittest.TestCase):
    def test_the_cast_marks_a_body_and_keeps_it(self):
        js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("function npcBodyLabel(npc)", js)
        self.assertIn('${body ? " isBody" : ""}', js)
        css = (ROOT / "static" / "styles.css").read_text(encoding="utf-8")
        self.assertIn(".castCard.isBody", css)


if __name__ == "__main__":
    unittest.main()
