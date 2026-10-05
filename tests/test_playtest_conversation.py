"""
Playtest #7 (major) and #6 (a), (c): who the player is talking to.

Turn 5 of the 2026-10-05 playtest revealed a hidden figure (the draft wrote
CAST interacting C, Ashwalker). Turn 6 was an untagged insult, "state your
business, if you came to intimidate you came to the wrong place...". The
active scene then listed Aria and Ashwalker both as "replies to the player",
the draft addressed Aria, and the paragraph writer put the player's words in
her mouth. The same turn's draft also wrote WALK northeast / MOVE Plains2 on
a talk line; the final prose stayed in The Back Lane and the engine moved the
player anyway (world.db: player at L2 Plains2, Aria and Ashwalker at L1).

app/conversation.py decides the addressee in the engine; these tests replay
the trace shapes:
  - the reveal on turn 5 makes the untagged turn-6 line go to Ashwalker;
  - a name in the line, a group phrase, an @tag and the chip each win in order;
  - every writing stage gets the answer, and it persists in SQLite;
  - a move the player did not ask for and the final prose does not show is dropped.
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-conversation-"))
os.environ.update(isolated_data_env(str(_TMP)))
os.environ.update(
    {
        "AI_RPG_PACK_DIR": str(_TMP / "packs"),
        "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
    }
)

from app import conversation as cv  # noqa: E402
from app import db, world  # noqa: E402
from app.db import connect  # noqa: E402

# Turn 5, as the trace recorded it.
TURN5_INPUT = 'i use @Swhispering_fates and say "come out now" commanding whatever is hiding to reveal itself'
TURN5_CAST = {"present": [], "interacting": ["C"], "off": [], "keywords": []}
TURN5_FINAL = (
    "You step into the dim alley, the flicker of your torch casting long, dancing shapes on the stone walls. "
    "You raise your hand and murmur, \"Come out now.\" The air seems to quiver, and then a shadow stirs from "
    "the darkest corner. Aria [[A]] narrows her glance, her lantern casting a flickering light that dances "
    "across the walls. \"What do you want, intruder?\" she asks, her grip on the lantern tightening.\n\n"
    "The figure's hooded head turns towards you, its sharp features casting dark silhouettes in the lantern "
    "light. \"Who are you, and what do you seek in the Back Lane?\" the figure demands, its tone cold and "
    "unwelcoming.\n\n"
    "Aria [[A]] steps closer, her lantern casting a warm glow that contrasts with the dim alley. \"Show "
    "yourself, whoever you are,\" she commands, her tone steady but authoritative. The figure's silhouette "
    "shifts, then the hood falls back, revealing a stern face. \"What business do you have here, Whisperer?\" "
    "Aria [[A]] demands, her hand resting on the hilt of her dagger."
)
# Turn 6.
TURN6_INPUT = (
    'i say "state your business, if you came to intimidate you came to the wrong place, standing in dark '
    "alleys is a quick way to get hurt, so its not the smartest idea, i wont hold it against you if you "
    "didn't know any better\" essentially insulting them while also making their actions look unintelligent."
)
TURN6_FINAL = (
    "Aria [[A]] narrows her icy blue stare at you, arms crossed over her chest. \"State your business, if you "
    "came to intimidate, you came to the wrong place.\" She leans back against the brick wall, one eyebrow "
    "raised. You can feel the tension in the air, the chill of the alley intensifying as her words settle "
    "around you.\n\n"
    "The Back Lane narrows around you, the cobblestones cold beneath your boots. You stand in a shadow cast by "
    "the towering buildings, the air thick with the scent of damp wood and forgotten secrets.\n\n"
    "You spit out your words with a sneer, the cold cobblestones reflecting the flickering streetlamp above. "
    "Ashwalker [[C]], a burly figure with a weathered face, shifts uncomfortably. \"Intimidate, you said? I was "
    "merely passing through when I heard your little exchange.\""
)
SCENE_BEFORE_5 = {"present": ["A"], "interacting": ["A"], "keywords": []}
SCENE_AFTER_5 = {"present": ["A", "C"], "interacting": ["A", "C"], "keywords": []}


def lane_context(settings: dict | None = None) -> dict:
    return {
        "current_location": {"id": 1, "code": "L1", "name": "The Back Lane"},
        "locations": [
            {
                "id": 1,
                "code": "L1",
                "name": "The Back Lane",
                "npcs": [
                    {"id": 1, "code": "A", "name": "Aria"},
                    {"id": 2, "code": "B", "name": "Quillwatch"},
                    {"id": 3, "code": "C", "name": "Ashwalker"},
                ],
            },
            {"id": 2, "code": "L2", "name": "Plains2", "npcs": [{"id": 4, "code": "D", "name": "Brannoc Vell"}]},
        ],
        "settings": settings if settings is not None else {"active_scene": dict(SCENE_BEFORE_5)},
    }


def after_turn5() -> dict:
    """The context the turn-6 line is resolved in: the engine has run turn 5's update."""
    ctx = lane_context()
    r5 = cv.resolve(ctx, TURN5_INPUT)
    state = cv.next_state(
        cv.load_state(ctx["settings"]),
        context=ctx,
        resolution=r5,
        scene_before=SCENE_BEFORE_5,
        scene_after=SCENE_AFTER_5,
        scene_cast=TURN5_CAST,
        narration=TURN5_FINAL,
        player_input=TURN5_INPUT,
        turn=5,
    )
    return lane_context({"active_scene": cv.synced_scene(SCENE_AFTER_5, state), "conversation": state})


class RevealThenUntaggedReply(unittest.TestCase):
    """#6 (a): after a reveal, the untagged line goes to the one revealed."""

    def test_turn5_reveal_sets_the_target(self):
        state = after_turn5()["settings"]["conversation"]
        self.assertEqual(state["revealed"], ["C"])
        self.assertEqual(state["target"], ["C"])
        self.assertEqual(state["why"], "revealed")
        # Aria spoke last in the prose; the reveal still wins.
        self.assertEqual(state["last_speaker"], "A")
        self.assertIn("A", state["present"])

    def test_turn6_insult_goes_to_ashwalker_not_aria(self):
        r6 = cv.resolve(after_turn5(), TURN6_INPUT)
        self.assertEqual(r6["addressed"], ["C"])
        self.assertEqual(r6["rule"], "revealed")
        self.assertEqual(r6["listening"], ["A"])
        self.assertTrue(r6["speech"])
        self.assertFalse(r6["group"], "bare 'them' must not make it a group line")

    def test_draft_note_names_one_answerer_and_the_listener(self):
        note = cv.model_note(cv.resolve(after_turn5(), TURN6_INPUT))
        self.assertIn("talking to Ashwalker [[C]]", note)
        self.assertIn("Only Ashwalker [[C]] answers", note)
        self.assertIn("listening", note)
        self.assertIn("Aria [[A]]", note)
        self.assertIn("player's quoted words are the player's own", note)

    def test_old_save_without_conversation_row_uses_newest_interacting(self):
        # The live game's row: {"present": ["A","C"], "interacting": ["A","C"]}.
        ctx = lane_context({"active_scene": dict(SCENE_AFTER_5)})
        self.assertEqual(cv.resolve(ctx, TURN6_INPUT)["addressed"], ["C"])


class ResolutionOrder(unittest.TestCase):
    def setUp(self):
        self.ctx = after_turn5()

    def test_name_in_text_beats_the_reveal(self):
        r = cv.resolve(self.ctx, "I ask Aria what she makes of this")
        self.assertEqual((r["addressed"], r["rule"]), (["A"], "name"))

    def test_named_topic_is_not_the_addressee(self):
        r = cv.resolve(self.ctx, "I ask Aria about Ashwalker")
        self.assertEqual(r["addressed"], ["A"])
        r = cv.resolve(self.ctx, 'i say "is Aria always this jumpy?"')
        self.assertEqual(r["addressed"], ["C"], "a name inside the quote is who the line is about")
        r = cv.resolve(self.ctx, "I point at Aria's lantern and laugh")
        self.assertEqual(r["addressed"], ["C"])

    def test_vocative_inside_quote_addresses(self):
        r = cv.resolve(self.ctx, '"Aria, stay behind me."')
        self.assertEqual((r["addressed"], r["rule"]), (["A"], "name"))
        r = cv.resolve(self.ctx, 'i say "stay back, Ashwalker."')
        self.assertEqual(r["addressed"], ["C"])

    def test_two_names_joined_after_a_cue(self):
        r = cv.resolve(self.ctx, 'i say "come here" to aria and ashwalker')
        self.assertEqual(r["addressed"], ["A", "C"])

    def test_npc_somewhere_else_is_never_the_addressee(self):
        r = cv.resolve(self.ctx, 'I tell Brannoc Vell "you owe me"')
        # Never the addressee while he is elsewhere; since playtest #31 he is
        # "called" (the writer is told who), and nobody present answers for him.
        self.assertEqual(r["addressed"], [])
        self.assertEqual((r["rule"], r["called"]), ("called", ["D"]))

    def test_group_phrase_addresses_everyone_present(self):
        r = cv.resolve(self.ctx, 'i say to everyone "calm down"')
        self.assertEqual((sorted(r["addressed"]), r["rule"], r["group"]), (["A", "C"], "group", True))
        self.assertIn("Any of them may answer", cv.model_note(r))
        r = cv.resolve(self.ctx, '"both of you, stop"')
        self.assertTrue(r["group"])

    def test_tag_overrides_everything(self):
        r = cv.resolve(self.ctx, 'i say to @Caria "is there danger close?"')
        self.assertEqual((r["addressed"], r["rule"]), (["A"], "tag"))
        r = cv.resolve(self.ctx, "@A what now? everyone is staring")
        self.assertEqual((r["addressed"], r["rule"]), (["A"], "tag"))
        r = cv.resolve(self.ctx, "i tell @Cashwalker that Aria is lying")
        self.assertEqual((r["addressed"], r["rule"]), (["C"], "tag"))
        # A skill tag is not a person.
        r = cv.resolve(self.ctx, TURN5_INPUT)
        self.assertNotEqual(r["rule"], "tag")

    def test_chip_choice_beats_the_reveal_but_not_a_name(self):
        state = dict(self.ctx["settings"]["conversation"])
        state.update({"target": ["A"], "chosen": True, "why": "chosen"})
        ctx = lane_context({"active_scene": self.ctx["settings"]["active_scene"], "conversation": state})
        self.assertEqual(cv.resolve(ctx, TURN6_INPUT)["rule"], "chosen")
        self.assertEqual(cv.resolve(ctx, TURN6_INPUT)["addressed"], ["A"])
        self.assertEqual(cv.resolve(ctx, "I glare at Ashwalker")["addressed"], ["C"])

    def test_answered_partner_keeps_the_target(self):
        """The player talked to Aria and she answered; a bystander's aside does not steal the next line."""
        ctx = self.ctx
        r = cv.resolve(ctx, 'i say to aria "who is he?"')
        prose = (
            "Aria [[A]] shrugs. \"A rag picker,\" she says. Ashwalker [[C]] snorts. \"I can hear you.\""
        )
        state = cv.next_state(
            ctx["settings"]["conversation"],
            context=ctx,
            resolution=r,
            scene_before=ctx["settings"]["active_scene"],
            scene_after=ctx["settings"]["active_scene"],
            scene_cast={},
            narration=prose,
            player_input='i say to aria "who is he?"',
            turn=7,
        )
        self.assertEqual(state["target"], ["A"])
        self.assertEqual(state["last_speaker"], "C")

    def test_nobody_answering_falls_to_last_speaker(self):
        ctx = lane_context({"active_scene": {"present": ["A", "C"], "interacting": []}, "conversation": {"target": []}})
        state = cv.next_state(
            cv.load_state(ctx["settings"]),
            context=ctx,
            resolution=cv.resolve(ctx, "I wait and watch"),
            scene_before=ctx["settings"]["active_scene"],
            scene_after=ctx["settings"]["active_scene"],
            scene_cast={},
            narration="Ashwalker [[C]] clears his throat. \"You still here?\"",
            player_input="I wait and watch",
            turn=8,
        )
        self.assertEqual((state["target"], state["why"]), (["C"], "last_speaker"))


class EveryWritingStageGetsIt(unittest.TestCase):
    """The draft, verify, paragraph and consolidation passes all read the same answer."""

    def setUp(self):
        self.ctx = after_turn5()
        self.ctx["conversation_turn"] = cv.resolve(self.ctx, TURN6_INPUT)

    def test_draft_footer_leads_with_the_conversation(self):
        text = world._expand_input_references(self.ctx, TURN6_INPUT)
        footer = text.split("Resolved player references:", 1)[1]
        self.assertTrue(footer.strip().startswith("Conversation (engine decided)"))
        self.assertNotIn("Active scene", footer)
        self.assertNotIn("interacting (replies to the player): Aria [[A]], Ashwalker", footer)

    def test_world_state_carries_conversation_and_hides_arias_old_line(self):
        from app.prompts import _visible_world

        self.ctx["conversations"] = [{"npc_name": "Aria", "npc_code": "A", "summary": "Is there need to be cautious?"}]
        view = _visible_world(self.ctx, TURN6_INPUT)
        self.assertEqual(view["conversation_turn"]["talking_to"], [{"name": "Ashwalker", "code": "C"}])
        self.assertEqual(view["conversation_turn"]["listening"], [{"name": "Aria", "code": "A"}])
        self.assertNotIn("conversations", view)

    def test_handoff_keeps_the_conversation(self):
        from app.llm import _clean_context_for_handoff

        cleaned = _clean_context_for_handoff(self.ctx, "test")
        self.assertEqual(cleaned["conversation_turn"]["addressed"], ["C"])

    def test_paragraph_brief_names_who_answers(self):
        from app.narration_pipeline import NarrationLedger, build_paragraph_briefs

        ledger = NarrationLedger(turn=6, player_input=TURN6_INPUT, budget={})
        briefs = build_paragraph_briefs({"paragraphs": 2}, self.ctx, TURN6_INPUT, ledger)
        self.assertEqual(briefs[0]["conversation"]["who_answers"], ["Ashwalker [[C]]"])
        self.assertEqual(briefs[0]["conversation"]["listening_only"], ["Aria [[A]]"])
        cover = " ".join(briefs[0]["must_cover"])
        self.assertIn("the player is talking to Ashwalker [[C]]", cover)
        self.assertEqual(briefs[0]["player_speech"][0]["speaker"], "player")


def seed_lane() -> None:
    db.init_db()
    with connect() as conn:
        conn.execute("DELETE FROM npcs")
        conn.execute("DELETE FROM settings WHERE key IN ('active_scene', 'conversation')")
        conn.execute("UPDATE locations SET name = 'The Back Lane' WHERE id = 1")
        for code, name in (("A", "Aria"), ("B", "Quillwatch"), ("C", "Ashwalker")):
            conn.execute("INSERT INTO npcs (code, location_id, name) VALUES (?, 1, ?)", (code, name))
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('active_scene', ?)",
            (json.dumps(SCENE_BEFORE_5),),
        )


class PersistsInSqlite(unittest.TestCase):
    def setUp(self):
        seed_lane()

    def _turn5(self):
        context = world.get_state(include_hidden=True)
        r5 = cv.resolve(context, TURN5_INPUT)
        with connect() as conn:
            before = cv.read_scene(conn)
            world._apply_scene_cast(conn, TURN5_CAST)
            cv.update_after_turn(
                conn,
                resolution=r5,
                scene_before=before,
                scene_cast=TURN5_CAST,
                narration=TURN5_FINAL,
                player_input=TURN5_INPUT,
                turn=5,
            )

    def test_turn5_update_is_stored_and_turn6_resolves_from_the_db(self):
        self._turn5()
        state = world.get_state(include_hidden=True)
        self.assertEqual(state["settings"]["conversation"]["target"], ["C"])
        # The old scene row agrees: interacting is the target, not a growing list.
        self.assertEqual(state["settings"]["active_scene"]["interacting"], ["C"])
        self.assertEqual(state["conversation"]["target"], [{"code": "C", "name": "Ashwalker"}])
        self.assertEqual(cv.resolve(state, TURN6_INPUT)["addressed"], ["C"])

    def test_saves_and_rewinds_carry_it(self):
        self._turn5()
        self.assertIn("conversation", world.SNAPSHOT_SETTING_KEYS)
        rows = world.export_world()["tables"]["settings"]
        stored = [row for row in rows if row.get("key") == "conversation"]
        self.assertEqual(len(stored), 1)
        self.assertEqual(json.loads(stored[0]["value"])["target"], ["C"])

    def test_chip_route_sets_and_clears(self):
        from app.main import ConversationTargetRequest, api_conversation_target
        from fastapi import HTTPException

        self._turn5()
        out = api_conversation_target(ConversationTargetRequest(codes=["A"]))
        self.assertEqual(out["conversation"]["target"], [{"code": "A", "name": "Aria"}])
        self.assertTrue(out["conversation"]["chosen"])
        self.assertEqual(cv.resolve(world.get_state(include_hidden=True), TURN6_INPUT)["rule"], "chosen")
        out = api_conversation_target(ConversationTargetRequest(codes=[], group=True))
        self.assertTrue(out["conversation"]["group"])
        out = api_conversation_target(ConversationTargetRequest(codes=[]))
        self.assertEqual(out["conversation"]["target"], [])
        with self.assertRaises(HTTPException):
            api_conversation_target(ConversationTargetRequest(codes=["Z"]))


class UnaskedMoveIsDropped(unittest.TestCase):
    """#6 (c): a talk turn's MOVE that the final prose never shows does not move the player."""

    def setUp(self):
        seed_lane()

    def _result(self):
        return {
            "narration": TURN6_FINAL,
            "player": {"move_to_location": "Plains2", "move_to_location_code": None},
            "map_walk": {"direction": "northeast", "steps": 1},
        }

    def test_turn6_move_is_dropped(self):
        result = self._result()
        with connect() as conn:
            report = world.resolve_movement(
                conn, result, TURN6_INPUT, intent=world._turn_intent(TURN6_INPUT)[0], narration=TURN6_FINAL
            )
        self.assertEqual(report["status"], "dropped_unshown")
        self.assertEqual(report["destination"], "Plains2")
        self.assertIsNone(result["player"]["move_to_location"])
        self.assertIsNone(result["map_walk"])

    def test_move_the_prose_shows_stands(self):
        prose = TURN6_FINAL + "\n\nYou head northeast out of the lane, Ashwalker trailing behind."
        result = self._result()
        with connect() as conn:
            report = world.resolve_movement(conn, result, TURN6_INPUT, intent="conversation", narration=prose)
        self.assertEqual(report["status"], "model")
        self.assertEqual(result["player"]["move_to_location"], "Plains2")

    def test_move_the_player_asked_for_stands(self):
        result = self._result()
        with connect() as conn:
            report = world.resolve_movement(conn, result, "I walk northeast", intent="travel", narration=TURN6_FINAL)
        self.assertEqual(report["status"], "model")


class PlayTurnWiring(unittest.TestCase):
    """End to end through play_turn with the model mocked: turn 6 as it was generated."""

    def setUp(self):
        seed_lane()
        PersistsInSqlite._turn5(self)

    def test_turn6_through_play_turn(self):
        seen: dict = {}

        def fake_generate(context, model_input):
            seen["conversation"] = context.get("conversation_turn")
            seen["model_input"] = model_input
            return {
                "scene_plan": {"goal": "talk", "focus_points": []},
                "narration_segments": [{"label": "scene", "text": TURN6_FINAL}],
                "narration": TURN6_FINAL,
                # What the turn-6 draft wrote: WALK northeast, MOVE Plains2.
                "player": {"move_to_location": "Plains2"},
                "map_walk": {"direction": "northeast", "steps": 1},
                "self_check": {"passed": True, "issues_found": [], "corrections_made": []},
                "turn_summary": "the player insults the stranger",
                "scene_focus": "dialogue",
            }

        with mock.patch.object(world, "generate_turn", side_effect=fake_generate):
            state = world.play_turn(TURN6_INPUT)["state"]
        self.assertEqual(seen["conversation"]["addressed"], ["C"])
        self.assertIn("talking to Ashwalker [[C]]", seen["model_input"])
        # The player stayed in the lane with the two people the scene is about.
        self.assertEqual((state.get("current_location") or {}).get("name"), "The Back Lane")
        self.assertEqual(state.get("movement", {}).get("status"), "dropped_unshown")
        # Ashwalker spoke last and was the one addressed: he stays the target.
        self.assertEqual(state["conversation"]["target"], [{"code": "C", "name": "Ashwalker"}])


if __name__ == "__main__":
    unittest.main()
