"""
Playtest #20 (major, ended the test): the scene thread was lost.

Game 2 ("Eldoria's Edge"). Turn 3: the player asked Aria to come along
("want to come with me? ..."), the quest parser accepted "Find hooded
figure", and the prose followed the figure down an alley and into a shop
while the journal said "Travel action with no MOVE op and no resolvable
destination; player stayed put". Turn 4, "Examine the herbs on the shop
counter": the draft had nothing about the pursuit, put Aria behind the
counter, brought in Elara with a well-repair message, and closed with "For
now, you decide to leave the well repairs for later and focus on the herbs."

app/scene_thread.py keeps what the player is in the middle of; these tests
replay the turn 3/4 shapes:
  - turn 3's accepted quest and the companion who went along become the thread;
  - turn 4's side action continues it, and the draft, verifier, paragraph
    writer, consolidator and suggestion ask all get it;
  - it is stored in SQLite, saved and rewound, and ends only when dropped,
    finished or stale;
  - following with no place named keeps the player here, and every stage is
    told so; a named place is followed;
  - a closing sentence that decides for the player is dropped.
"""
from __future__ import annotations

import json
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-scene-thread-"))
os.environ.update(isolated_data_env(str(_TMP)))
os.environ.update(
    {
        "AI_RPG_PACK_DIR": str(_TMP / "packs"),
        "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
    }
)

from app import conversation as cv  # noqa: E402
from app import db, llm, world  # noqa: E402
from app import scene_thread as st  # noqa: E402
from app.db import connect  # noqa: E402

# Turn 3, as the trace recorded it.
TURN3_INPUT = (
    'i say to @Caria "want to come with me? if anything happens you should go and get help though, '
    'but im just as curious"'
)
TURN3_FINAL = (
    "You approach Aria [[A]], the baker, and ask, \"Want to come with me? If anything happens, you should go "
    "and get help, but I'm just as curious.\" Aria [[A]] looks at you, her expression thoughtful, then nods. "
    "\"I can see that. Let's follow the hooded figure, but stay alert.\" You turn to leave, and Aria [[A]] "
    "follows behind you. The two of you make your way cautiously through the crowded streets of Eldoria's "
    "Edge [[L1]], keeping an eye out for any signs of the hooded figure.\n\n"
    "Suddenly, the hooded figure disappears into a narrow alleyway. You exchange a glance with Aria [[A]], and "
    "she nods for you to follow. The alley is dimly lit, but you can make out the figure at the end. The "
    "hooded figure disappears into a small shop, and you hesitate. Aria [[A]] steps forward and knocks gently "
    "on the door."
)
TURN3_QUEST_REPORT = {"status": "applied", "source": "parser", "created": [], "updated": [{"code": "Q1", "action": "accept"}], "rejected": []}
# Turn 4.
TURN4_INPUT = "Examine the herbs on the shop counter"
TURN4_FINAL = (
    "You step closer to the shop counter, where a small pile of dried herbs lies. The aroma of thyme and "
    "lavender wafts up. Aria [[A]], the baker, leans over her work. \"Would you like to know more about "
    "these?\" she asks.\n\n"
    "Aria [[A]] takes the message and nods. \"Thank you, Elara [[D]]. I'll make sure it's delivered.\" She "
    "then turns back to you, her expression thoughtful. \"The well is important for our water supply.\" You "
    "feel a slight pressure to help, but the shop is a place of commerce, not direct action. For now, you "
    "decide to leave the well repairs for later and focus on the herbs."
)


def edge_context(settings: dict | None = None) -> dict:
    return {
        "current_location": {"id": 1, "code": "L1", "name": "Eldoria's Edge"},
        "locations": [
            {
                "id": 1,
                "code": "L1",
                "name": "Eldoria's Edge",
                "npcs": [
                    {"id": 1, "code": "A", "name": "Aria", "role": "baker"},
                    {"id": 2, "code": "B", "name": "Dockwick", "role": "well keeper"},
                    {"id": 3, "code": "C", "name": "Hearthbin", "role": "message runner"},
                ],
            }
        ],
        "settings": settings if settings is not None else {},
    }


QUEST_Q1 = {"code": "Q1", "title": "Find hooded figure", "status": "active", "step": "Get more information about the hooded figure."}


def thread_after_turn3() -> dict:
    ctx = edge_context()
    talk = cv.resolve(ctx, TURN3_INPUT)
    turn_thread = st.begin_turn(ctx, TURN3_INPUT, talk)
    return st.next_thread(
        turn_thread,
        None,
        quest_report=TURN3_QUEST_REPORT,
        quests={"Q1": dict(QUEST_Q1)},
        narration=TURN3_FINAL,
        player_input=TURN3_INPUT,
        location="Eldoria's Edge",
        turn=3,
    )


class Turn3BecomesTheThread(unittest.TestCase):
    def test_invitation_carries_who_was_asked(self):
        ctx = edge_context()
        turn_thread = st.begin_turn(ctx, TURN3_INPUT, cv.resolve(ctx, TURN3_INPUT))
        self.assertEqual(turn_thread["status"], "none")
        self.assertEqual(turn_thread["asked_along"], [{"code": "A", "name": "Aria"}])

    def test_accepted_quest_and_aria_make_the_thread(self):
        thread = thread_after_turn3()
        self.assertEqual(thread["doing"], "Find hooded figure")
        self.assertEqual(thread["target"], "the hooded figure")
        self.assertEqual(thread["with"], [{"code": "A", "name": "Aria"}])
        self.assertEqual(thread["quest"]["code"], "Q1")
        self.assertEqual(thread["quest"]["step"], QUEST_Q1["step"])
        self.assertEqual(thread["where"], "Eldoria's Edge")

    def test_a_refusal_is_not_a_companion(self):
        ctx = edge_context()
        turn_thread = st.begin_turn(ctx, TURN3_INPUT, cv.resolve(ctx, TURN3_INPUT))
        refused = "Aria [[A]] shakes her head and will not come with you. You set off after the hooded figure alone."
        thread = st.next_thread(
            turn_thread, None, quest_report=TURN3_QUEST_REPORT, quests={"Q1": dict(QUEST_Q1)},
            narration=refused, player_input=TURN3_INPUT, location="Eldoria's Edge", turn=3,
        )
        self.assertEqual(thread["with"], [])

    def test_the_players_own_pursuit_starts_a_thread(self):
        ctx = edge_context()
        turn_thread = st.begin_turn(ctx, "I follow the hooded figure down the alley", None)
        self.assertEqual(turn_thread["status"], "started")
        self.assertEqual(turn_thread["target"], "the hooded figure")
        self.assertEqual(turn_thread["doing"], "follow the hooded figure")

    def test_following_a_person_here_keeps_their_code(self):
        ctx = edge_context()
        turn_thread = st.begin_turn(ctx, "I follow Dockwick", None)
        self.assertEqual(turn_thread["target_code"], "B")


class Turn4SideActionStaysInside(unittest.TestCase):
    """The herbs line happens inside the pursuit, and every stage is told so."""

    def setUp(self):
        stored = thread_after_turn3()
        self.ctx = edge_context({st.SETTING_KEY: stored})
        self.ctx["conversation_turn"] = cv.resolve(self.ctx, TURN4_INPUT)
        self.ctx["scene_thread"] = st.begin_turn(self.ctx, TURN4_INPUT, self.ctx["conversation_turn"])

    def test_side_action_continues_the_thread(self):
        self.assertEqual(self.ctx["scene_thread"]["status"], "continues")
        self.assertEqual(self.ctx["scene_thread"]["target"], "the hooded figure")

    def test_draft_world_state_and_instruction(self):
        from app.prompts import _visible_world, build_user_prompt, build_verify_prompt

        view = _visible_world(self.ctx, TURN4_INPUT)
        thread = view["scene_thread"]
        self.assertEqual(thread["doing"], "Find hooded figure")
        self.assertEqual(thread["target"], {"name": "the hooded figure"})
        self.assertEqual(thread["with_the_player"], [{"name": "Aria", "code": "A"}])
        self.assertEqual(thread["quest"]["code"], "Q1")
        self.assertIn("inside it", thread["this_turn"])
        draft = json.loads(build_user_prompt(self.ctx, TURN4_INPUT))
        self.assertIn("does not end it", draft["instruction"])
        self.assertNotIn("is an issue", draft["instruction"].split("scene_thread", 1)[1].split("world_facts")[0])
        verify = json.loads(build_verify_prompt(self.ctx, TURN4_INPUT, {"narration": "x"}))
        self.assertIn("scene_thread", verify["world_state"])
        self.assertIn("forgets scene_thread on a side action", verify["instruction"])

    def test_handoff_keeps_the_thread(self):
        cleaned = llm._clean_context_for_handoff(self.ctx, "test")
        self.assertEqual(cleaned["scene_thread"]["target"], "the hooded figure")

    def test_paragraph_brief_and_writer_prompt(self):
        from app.narration_pipeline import NarrationLedger, build_paragraph_briefs

        ledger = NarrationLedger(turn=4, player_input=TURN4_INPUT, budget={})
        briefs = build_paragraph_briefs({"paragraphs": 2}, self.ctx, TURN4_INPUT, ledger)
        for brief in briefs:
            self.assertEqual(brief["scene_thread"]["after"], "the hooded figure")
            self.assertEqual(brief["scene_thread"]["with_the_player"], ["Aria [[A]]"])
        self.assertIn("do not decide anything for the player", " ".join(briefs[-1]["must_cover"]))
        seen = {}

        def fake_chat(system, user, **kwargs):
            seen["system"] = system
            return "You run a thumb over the dried mint."

        with mock.patch.object(llm, "_chat_text", side_effect=fake_chat):
            writer = llm._make_pipeline_paragraph_writer([], None, 30, self.ctx)
            writer(briefs[0], "", ledger)
        self.assertIn("scene_thread is what the player is in the middle of", seen["system"])
        self.assertIn("never write that they decide", seen["system"])

    def test_consolidator_gets_the_thread(self):
        seen = {}

        def fake_chat(system, user, **kwargs):
            seen["payload"] = json.loads(user)
            return "===P1===\nOne.\n===P2===\nTwo."

        from app.narration_pipeline import NarrationLedger

        with mock.patch.object(llm, "_chat_text", side_effect=fake_chat):
            consolidate = llm._make_pipeline_consolidator([], None, 30, self.ctx)
            consolidate(["One.", "Two."], NarrationLedger(turn=4, player_input=TURN4_INPUT, budget={}))
        self.assertEqual(seen["payload"]["scene_thread"]["after"], "the hooded figure")

    def test_suggestions_continue_the_thread(self):
        captured = {}

        def fake_json(system, user, **kwargs):
            captured["prompt"] = json.loads(user)
            return {"suggestions": ["Ask Aria where the hooded figure went", "Check the back door", "Buy mint"]}

        ctx = dict(self.ctx)
        ctx["scene_thread"] = st.load(self.ctx["settings"])
        ctx["last_narration"] = TURN4_FINAL
        with mock.patch.object(llm, "_chat_json", side_effect=fake_json):
            llm.generate_input_suggestions(ctx)
        scene = captured["prompt"]["scene"]
        self.assertEqual(scene["thread"]["after"], "the hooded figure")
        self.assertEqual(scene["thread"]["with"], ["Aria"])
        self.assertTrue(any("scene.thread" in rule and "at least one" in rule for rule in captured["prompt"]["rules"]))
        with mock.patch.object(llm, "_chat_json", side_effect=lambda s, u, **k: captured.update(prompt=json.loads(u)) or {"action": "Go", "why": "x"}):
            llm.generate_input_suggestions(ctx, deeper=True)
        self.assertIn("thread", captured["prompt"]["scene"])
        self.assertTrue(any("scene.thread" in rule for rule in captured["prompt"]["rules"]))


class ThreadEnds(unittest.TestCase):
    def _next(self, previous, player_input, *, report=None, narration="", turn=5, quests=None):
        ctx = edge_context({st.SETTING_KEY: previous})
        turn_thread = st.begin_turn(ctx, player_input, None)
        return st.next_thread(
            turn_thread, previous, quest_report=report or {}, quests=quests or {"Q1": dict(QUEST_Q1)},
            narration=narration, player_input=player_input, location="Eldoria's Edge", turn=turn,
        )

    def test_player_drops_it(self):
        self.assertIsNone(self._next(thread_after_turn3(), "forget the hooded figure, let's get a drink"))

    def test_stop_following_never_starts_one(self):
        self.assertIsNone(st.begin_turn(edge_context(), "I stop following him", None))

    def test_quest_complete_ends_it(self):
        report = {"updated": [{"code": "Q1", "action": "complete"}]}
        self.assertIsNone(self._next(thread_after_turn3(), "I hand over the cloak", report=report))

    def test_side_actions_do_not_end_it_but_staleness_does(self):
        thread = thread_after_turn3()
        for turn in range(4, 4 + st.STALE_TURNS - 1):
            thread = self._next(thread, TURN4_INPUT, narration="The mint smells sharp.", turn=turn)
            self.assertIsNotNone(thread)
        self.assertIsNone(self._next(thread, TURN4_INPUT, narration="The mint smells sharp.", turn=3 + st.STALE_TURNS))

    def test_a_mention_keeps_it_fresh(self):
        thread = thread_after_turn3()
        thread = self._next(thread, TURN4_INPUT, narration="Through the window, the hooded figure slips past.", turn=12)
        self.assertEqual(thread["touched_turn"], 12)


def seed_edge() -> None:
    db.init_db()
    with connect() as conn:
        conn.execute("DELETE FROM npcs")
        conn.execute("DELETE FROM quests")
        conn.execute("DELETE FROM quest_steps")
        conn.execute("DELETE FROM settings WHERE key IN ('active_scene', 'conversation', 'scene_thread')")
        conn.execute("UPDATE locations SET name = 'Eldoria''s Edge' WHERE id = 1")
        for code, name, role in (("A", "Aria", "baker"), ("B", "Dockwick", "well keeper"), ("C", "Hearthbin", "message runner")):
            conn.execute("INSERT INTO npcs (code, location_id, name, role) VALUES (?, 1, ?, ?)", (code, name, role))
        conn.execute(
            "INSERT INTO quests (code, title, description, status, current_step, total_steps) "
            "VALUES ('Q1', 'Find hooded figure', 'Investigate the hooded figure seen at the market.', 'active', 1, 1)"
        )
        quest_id = conn.execute("SELECT id FROM quests WHERE code = 'Q1'").fetchone()[0]
        conn.execute(
            "INSERT INTO quest_steps (quest_id, step_number, title, description, status) "
            "VALUES (?, 1, 'Talk to Aria', 'Get more information about the hooded figure.', 'active')",
            (quest_id,),
        )


def store_turn3() -> None:
    context = world.get_state(include_hidden=True)
    talk = cv.resolve(context, TURN3_INPUT)
    with connect() as conn:
        st.update_after_turn(
            conn,
            turn_thread=st.begin_turn(context, TURN3_INPUT, talk),
            quest_report=TURN3_QUEST_REPORT,
            narration=TURN3_FINAL,
            player_input=TURN3_INPUT,
            turn=3,
        )


def fake_turn(narration: str, **extra):
    def fake_generate(context, model_input):
        fake_generate.seen = {"context": context, "model_input": model_input}
        return {
            "scene_plan": {"goal": "look", "focus_points": []},
            "narration_segments": [{"label": "scene", "text": narration}],
            "narration": narration,
            "player": {},
            "self_check": {"passed": True, "issues_found": [], "corrections_made": []},
            "turn_summary": "the player looks around",
            "scene_focus": "action",
            **extra,
        }

    return fake_generate


class PersistsInSqlite(unittest.TestCase):
    def setUp(self):
        seed_edge()
        store_turn3()

    def test_stored_and_read_back(self):
        state = world.get_state(include_hidden=True)
        self.assertEqual(state["scene_thread"]["target"], "the hooded figure")
        self.assertEqual(state["scene_thread"]["quest"]["step"], "Get more information about the hooded figure.")
        self.assertEqual(state["scene_thread"]["with"], [{"code": "A", "name": "Aria"}])

    def test_saves_carry_it(self):
        self.assertIn("scene_thread", world.SNAPSHOT_SETTING_KEYS)
        rows = world.export_world()["tables"]["settings"]
        stored = [row for row in rows if row.get("key") == "scene_thread"]
        self.assertEqual(json.loads(stored[0]["value"])["doing"], "Find hooded figure")

    def test_turn4_through_play_turn_keeps_the_thread(self):
        fake = fake_turn(TURN4_FINAL)
        with mock.patch.object(world, "generate_turn", side_effect=fake):
            state = world.play_turn(TURN4_INPUT)["state"]
        seen = fake.seen["context"]["scene_thread"]
        self.assertEqual(seen["status"], "continues")
        self.assertEqual(seen["target"], "the hooded figure")
        self.assertEqual(state["scene_thread"]["target"], "the hooded figure")
        self.assertEqual(state["scene_thread"]["with"], [{"code": "A", "name": "Aria"}])

    def test_rewind_brings_a_dropped_thread_back(self):
        fake = fake_turn("You shrug and let the matter rest, turning back toward the square.")
        with mock.patch.object(world, "generate_turn", side_effect=fake):
            state = world.play_turn("forget the hooded figure")["state"]
        self.assertIsNone(state["scene_thread"])
        world.rewind_last_turn()
        self.assertEqual(world.get_state(include_hidden=True)["scene_thread"]["target"], "the hooded figure")


class FollowingWithoutAPlace(unittest.TestCase):
    """Prose and position agree: follow to a named place, else stay and say so."""

    FOLLOW = "I follow the hooded figure"

    def setUp(self):
        seed_edge()
        with connect() as conn:
            conn.execute("DELETE FROM locations WHERE id != 1")
            conn.execute("INSERT INTO locations (code, name, summary) VALUES ('L2', 'Saltmarsh Quay', 'docks')")

    def test_follow_is_travel(self):
        self.assertTrue(world.travel_intent("I chase the hooded figure"))

    def test_no_place_named_stays_and_says_so(self):
        prose = "You slip after the hooded figure through the crowd, keeping Aria close. It ducks into an alley."
        result = {"narration": prose, "player": {}}
        with connect() as conn:
            report = world.resolve_movement(conn, result, self.FOLLOW, intent="travel", narration=prose)
        self.assertEqual(report["status"], "unresolved")
        self.assertEqual(report["follow"], "the hooded figure")
        self.assertEqual(report["stayed_in"], "Eldoria's Edge")
        self.assertFalse(result["player"].get("move_to_location_code"))

    def test_named_place_is_followed(self):
        prose = "You follow the hooded figure out past the gate and down to Saltmarsh Quay, where it stops."
        result = {"narration": prose, "player": {}}
        with connect() as conn:
            report = world.resolve_movement(conn, result, self.FOLLOW, intent="travel", narration=prose)
        self.assertEqual(report["status"], "repaired")
        self.assertEqual(report["rule"], "follow_named")
        self.assertEqual(result["player"]["move_to_location_code"], "L2")

    def test_journal_says_where_the_player_stayed(self):
        prose = "You slip after the hooded figure through the crowd. It ducks into an alley and is gone."
        with mock.patch.object(world, "generate_turn", side_effect=fake_turn(prose)):
            state = world.play_turn(self.FOLLOW)["state"]
        self.assertEqual((state.get("current_location") or {}).get("name"), "Eldoria's Edge")
        with connect() as conn:
            notes = [r[0] for r in conn.execute("SELECT content FROM journal WHERE kind = 'system'").fetchall()]
        self.assertTrue(any("Followed the hooded figure with no place named" in n for n in notes), notes)

    def test_draft_is_told_the_player_stays(self):
        from app.prompts import _visible_world, build_user_prompt
        from app.turn_dsl import build_dsl_user_prompt

        context = world.build_prompt_context(world.get_state(include_hidden=True), self.FOLLOW)
        view = _visible_world(context, self.FOLLOW)
        contract = view["movement_contract"]
        self.assertIn("still in Eldoria's Edge", contract["no_move_means"])
        self.assertEqual(contract["following"], "the hooded figure")
        self.assertIn("no_move_means holds", json.loads(build_user_prompt(context, self.FOLLOW))["instruction"])
        dsl = build_dsl_user_prompt(context, self.FOLLOW)
        self.assertIn("Without a MOVE the player is still in Eldoria's Edge", dsl)
        self.assertIn("The player goes after the hooded figure", dsl)

    def test_turn3_writer_keeps_the_player_here(self):
        from app.narration_pipeline import NarrationLedger, build_paragraph_briefs

        context = world.build_prompt_context(world.get_state(include_hidden=True), TURN3_INPUT)
        self.assertTrue(context["movement_contract"]["travel_intent"])
        draft = {"narration": TURN3_FINAL, "player": {"move_to_location": None}}
        ledger = NarrationLedger(turn=3, player_input=TURN3_INPUT, budget={})
        briefs = build_paragraph_briefs({"paragraphs": 2}, context, TURN3_INPUT, ledger, draft=draft)
        self.assertEqual(briefs[0]["scene_facts"]["player_stays_in"], "Eldoria's Edge")
        moved = {"narration": TURN3_FINAL, "player": {"move_to_location": "Saltmarsh Quay"}}
        briefs = build_paragraph_briefs({"paragraphs": 2}, context, TURN3_INPUT, ledger, draft=moved)
        self.assertNotIn("player_stays_in", briefs[0]["scene_facts"])
        named = "I walk to Saltmarsh Quay"
        briefs = build_paragraph_briefs({"paragraphs": 2}, world.build_prompt_context(world.get_state(include_hidden=True), named), named, ledger, draft=draft)
        self.assertNotIn("player_stays_in", briefs[0]["scene_facts"])


class NarrationNeverChoosesForThePlayer(unittest.TestCase):
    def test_turn4_closing_decision_is_dropped(self):
        turn = {
            "narration": TURN4_FINAL,
            "narration_segments": [{"label": "paragraph", "text": p} for p in TURN4_FINAL.split("\n\n")],
            "self_check": {"corrections_made": []},
        }
        out = llm._drop_decided_choice(turn, TURN4_INPUT)
        self.assertNotIn("you decide", out["narration"].lower())
        self.assertTrue(out["narration"].endswith("not direct action."))
        self.assertEqual(len(out["narration_segments"]), 2)
        self.assertIn("made a choice for the player", out["self_check"]["corrections_made"][-1])

    def test_the_players_own_decision_stands(self):
        text = "x" * 300 + ". You decide to wait for Aria by the door."
        out = llm._drop_decided_choice({"narration": text}, "I decide to wait for Aria by the door")
        self.assertEqual(out["narration"], text)

    def test_open_situation_and_speech_stand(self):
        for last in (
            "Whatever you decide to do, the door stays shut.",
            "\"You decide to trust him, then?\" Aria asks.",
        ):
            text = "x" * 300 + ". " + last
            self.assertEqual(llm._drop_decided_choice({"narration": text}, TURN4_INPUT)["narration"], text)

    def test_quality_pass_applies_it(self):
        turn = {"narration": TURN4_FINAL}
        with mock.patch.object(llm, "pipeline_enabled", return_value=False), \
                mock.patch.object(llm, "_ensure_narration_depth", side_effect=lambda t, *a, **k: t), \
                mock.patch.object(llm, "_ensure_narration_voice", side_effect=lambda t, *a, **k: t), \
                mock.patch.object(llm, "_ensure_answer_act", side_effect=lambda t, *a, **k: t), \
                mock.patch.object(llm, "_ensure_recall_specifics", side_effect=lambda t, *a, **k: t):
            out = llm._ensure_narration_quality(turn, {}, TURN4_INPUT, "", 30, [], "draft")
        self.assertNotIn("you decide", out["narration"].lower())

    def test_the_ask_has_no_sample_closer(self):
        from app.prompts import PROSE_VOICE

        self.assertIn("The player makes every choice", PROSE_VOICE)
        self.assertNotIn("you decide to", PROSE_VOICE.lower())


if __name__ == "__main__":
    unittest.main()
