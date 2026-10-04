"""The quest parser: the narrator offers work in prose, the engine instates it.

Traces showed the story handing the player concrete jobs ("You've been tasked
with escorting a shipment of silk from here to the western border") that never
became a quest row: the turn model had no way to create one. ``app.quest_parser``
gates cheaply on job language, builds a small parser prompt, and validates and
applies what the parser proposes against the live database.

Run:  python -m unittest tests.test_quest_parser
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-quest-parser-test-"))
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

from app import db, quest_parser as qp, world  # noqa: E402
from app.quests import get_offered_quests  # noqa: E402

SILK = (
    "The carter wipes his hands on his apron and looks you over. "
    "\"You've been tasked with escorting a shipment of silk from here to the western border,\" Carter says. "
    "\"Forty silver when it arrives whole.\""
)
SCENERY = (
    "Rain runs off the slate roofs and pools between the cobbles. A dog sleeps under the cart, "
    "and the smell of bread drifts from the bakery on the corner."
)
CANNED_SILK_REPLY = json.dumps(
    {
        "new": [
            {
                "title": "Escort the silk to the western border",
                "summary": "Carter wants the silk shipment escorted west.",
                "giver": "Carter",
                "status": "offered",
                "steps": [{"title": "Escort the silk shipment", "description": "Guard it on the road", "location": "Western Border"}],
                "reward": {"gold": 40, "xp": 0, "items": [], "text": "Forty silver when it arrives whole"},
                "difficulty": "normal",
                "timer_turns": 0,
                "evidence": "escorting a shipment of silk from here to the western border",
            }
        ],
        "updates": [],
    }
)


def setUpModule():
    os.environ.update(_ENV)
    assert str(db.db_path()).startswith(str(_TMP)), db.db_path()
    db.init_db()


def _fresh_world_with_carter() -> None:
    db.init_db()
    world.start_playthrough({"player_name": "Ash", "start_location": "Low Gate", "special_ability_origin": "none"})
    with db.connect() as conn:
        loc = conn.execute("SELECT id FROM locations ORDER BY id LIMIT 1").fetchone()
        conn.execute(
            "INSERT INTO npcs (code, location_id, name, role) VALUES (?, ?, ?, ?)",
            ("A9", int(loc["id"]), "Carter", "carter"),
        )


def _turn(narration: str, **extra) -> dict:
    text = " ".join([narration] + [SCENERY] * 6)
    return {
        "scene_plan": {"goal": "talk", "focus_points": []},
        "narration_segments": [{"label": "scene", "text": text}],
        "narration": text,
        "player": {},
        "self_check": {"passed": True, "issues_found": [], "corrections_made": []},
        "turn_summary": "a beat",
        "scene_focus": "dialogue",
        **extra,
    }


class TestTheGate(unittest.TestCase):
    def test_a_job_offer_opens_the_gate(self):
        self.assertTrue(qp.needs_quest_parse(SILK))
        self.assertTrue(qp.needs_quest_parse("\"Bring me the ledger before dawn and I'll pay you well.\""))

    def test_scenery_does_not(self):
        self.assertFalse(qp.needs_quest_parse(SCENERY))
        self.assertFalse(qp.needs_quest_parse("The job of the gatehouse is to keep the river out, and it does."))

    def test_marks_and_accepting_an_open_offer_do(self):
        self.assertTrue(qp.needs_quest_parse(SCENERY, marks=[{"op": "QUEST", "title": "x"}]))
        offers = [{"code": "Q1", "title": "A parcel to carry", "status": "offered"}]
        self.assertTrue(qp.needs_quest_parse(SCENERY, "I'll take the job.", open_offers=offers))
        self.assertFalse(qp.needs_quest_parse(SCENERY, "I look around.", open_offers=offers))

    def test_progress_on_an_active_quest_does(self):
        active = [{"code": "Q2", "title": "Escort the silk to the western border", "status": "active"}]
        self.assertTrue(qp.needs_quest_parse("You hand the silk over at the border post; it is delivered.", active_quests=active))


class TestThePrompt(unittest.TestCase):
    def test_shape_rules_and_no_example_titles(self):
        system, user = qp.build_parser_prompt(
            SILK, "hello", npcs=[{"code": "A9", "name": "Carter", "role": "carter"}], locations=[{"code": "L1", "name": "Low Gate"}]
        )
        self.assertIn("JSON only", system)
        data = json.loads(user)
        self.assertIn("return_shape", data)
        self.assertEqual(data["known_npcs"][0]["name"], "Carter")
        self.assertTrue(any("word for word" in rule for rule in data["rules"]))
        # Placeholders describe; they never name a job a small model could paste.
        title_hint = data["return_shape"]["new"][0]["title"]
        self.assertNotIn("silk", title_hint.lower())


class TestParseReply(unittest.TestCase):
    def test_coercions(self):
        self.assertEqual(qp.parse_reply("```json\n{\"new\": [], \"updates\": []}\n```"), {"new": [], "updates": []})
        out = qp.parse_reply({"quests": {"title": "x"}, "quest_updates": [{"quest": "Q1"}, "junk"]})
        self.assertEqual(len(out["new"]), 1)
        self.assertEqual(len(out["updates"]), 1)
        self.assertEqual(qp.parse_reply("Sure! {\"new\": [{\"title\": \"a\"}]} hope that helps")["new"][0]["title"], "a")
        self.assertEqual(qp.parse_reply("not json at all"), {"new": [], "updates": []})
        self.assertEqual(qp.parse_reply(None), {"new": [], "updates": []})
        many = {"new": [{"title": str(i)} for i in range(9)]}
        self.assertEqual(len(qp.parse_reply(many)["new"]), qp.MAX_NEW_PER_TURN)


class TestMergeMarks(unittest.TestCase):
    def test_marks_fold_in_and_set_source(self):
        marks = [{"op": "QUEST", "title": "Find the miller", "giver": "A9", "step": "Ask at the mill", "evidence": "find the miller"}]
        merged = qp.merge_marks({"new": [], "updates": []}, marks)
        self.assertEqual(merged["source"], "marks")
        self.assertEqual(merged["new"][0]["title"], "Find the miller")
        merged = qp.merge_marks(qp.parse_reply(CANNED_SILK_REPLY), marks + [{"op": "QUEST_DONE", "quest": "Q1", "action": "step_done"}])
        self.assertEqual(merged["source"], "parser+marks")
        self.assertEqual(len(merged["new"]), 2)
        self.assertEqual(merged["updates"][0]["action"], "step_done")


class TestValidation(unittest.TestCase):
    NPCS = [{"id": 9, "code": "A9", "name": "Carter", "role": "carter"}]

    def _validate(self, changes, narration=SILK, player_input="", existing=None):
        return qp.validate_quest_changes(changes, narration=narration, player_input=player_input, npcs=self.NPCS, locations=[], existing=existing or [])

    def test_the_silk_offer_is_accepted_as_offered(self):
        accepted, rejected = self._validate(qp.parse_reply(CANNED_SILK_REPLY))
        self.assertEqual(rejected, [])
        item = accepted["new"][0]
        self.assertEqual(item["status"], "offered")
        self.assertEqual(item["giver_npc_id"], 9)
        self.assertEqual(item["reward"]["gold"], 40)

    def test_ungrounded_evidence_is_rejected(self):
        reply = qp.parse_reply(CANNED_SILK_REPLY)
        reply["new"][0]["evidence"] = "slay the dragon of the eastern peaks"
        accepted, rejected = self._validate(reply)
        self.assertEqual(accepted["new"], [])
        self.assertIn("evidence_not_in_text", rejected[0]["reasons"])

    def test_unknown_giver_is_rejected_but_a_board_is_fine(self):
        reply = qp.parse_reply(CANNED_SILK_REPLY)
        reply["new"][0]["giver"] = "Lord Nobody"
        self.assertIn("unknown_giver", self._validate(reply)[1][0]["reasons"])
        reply["new"][0]["giver"] = "the notice board"
        self.assertEqual(self._validate(reply)[1], [])

    def test_a_duplicate_of_an_open_quest_is_rejected(self):
        existing = [{"id": 3, "code": "Q3", "title": "Escort the silk to the western border", "status": "offered"}]
        rejected = self._validate(qp.parse_reply(CANNED_SILK_REPLY), existing=existing)[1]
        self.assertTrue(any(r.startswith("duplicate_of") for r in rejected[0]["reasons"]))

    def test_active_only_when_the_player_accepts(self):
        reply = qp.parse_reply(CANNED_SILK_REPLY)
        reply["new"][0]["status"] = "active"
        self.assertEqual(self._validate(reply)[0]["new"][0]["status"], "offered")
        self.assertEqual(self._validate(reply, player_input="I'll take the job.")[0]["new"][0]["status"], "active")

    def test_update_transitions(self):
        existing = [
            {"id": 1, "code": "Q1", "title": "A parcel to carry", "status": "offered"},
            {"id": 2, "code": "Q2", "title": "The missing grain", "status": "active"},
        ]
        narration = "You hand the grain sacks over to the miller. The parcel is still on the board."
        changes = {
            "updates": [
                {"quest": "Q1", "action": "step_done", "evidence": "The parcel is still on the board"},
                {"quest": "Q2", "action": "step_done", "evidence": "You hand the grain sacks over to the miller"},
                {"quest": "Q9", "action": "complete", "evidence": "x"},
                {"quest": "Q1", "action": "accept", "evidence": ""},
            ]
        }
        accepted, rejected = self._validate(changes, narration=narration, player_input="I'll take the job", existing=existing)
        self.assertEqual([(u["code"], u["action"]) for u in accepted["updates"]], [("Q2", "step_done"), ("Q1", "accept")])
        reasons = [r["reasons"] for r in rejected]
        self.assertTrue(any(any(x.startswith("illegal_transition") for x in r) for r in reasons))
        self.assertTrue(any("unknown_quest" in r for r in reasons))


class TestApplyThroughTheTurn(unittest.TestCase):
    def setUp(self):
        _fresh_world_with_carter()

    def test_the_silk_escort_becomes_an_offered_quest_from_carter(self):
        changes = qp.parse_reply(CANNED_SILK_REPLY)
        changes["source"] = "parser"
        state = world.apply_turn(_turn(SILK, quest_changes=changes), "Talk to the carter")
        report = state["quest_report"]
        self.assertEqual(report["status"], "applied", report)
        code = report["created"][0]["code"]
        with db.connect() as conn:
            row = conn.execute("SELECT * FROM quests WHERE code = ?", (code,)).fetchone()
            steps = conn.execute("SELECT * FROM quest_steps WHERE quest_id = ?", (row["id"],)).fetchall()
            giver = conn.execute("SELECT name FROM npcs WHERE id = ?", (row["giver_npc_id"],)).fetchone()
            journal = [r["content"] for r in conn.execute("SELECT content FROM journal WHERE kind = 'quest'").fetchall()]
            offered = get_offered_quests(conn)
        self.assertEqual(row["status"], "offered")
        self.assertEqual(row["reward_gold"], 40)
        self.assertIn("parser:parser", row["notes"])
        self.assertEqual(len(steps), 1)
        self.assertEqual(giver["name"], "Carter")
        self.assertTrue(any("New job offered: Escort the silk" in j for j in journal), journal)
        self.assertEqual(offered[0]["giver_name"], "Carter")
        self.assertTrue(any(o["title"].startswith("Escort the silk") for o in state["open_quest_offers"]))

    def test_accept_then_complete_pays_the_reward(self):
        changes = qp.parse_reply(CANNED_SILK_REPLY)
        world.apply_turn(_turn(SILK, quest_changes=changes), "Talk to the carter")
        with db.connect() as conn:
            code = conn.execute("SELECT code FROM quests ORDER BY id DESC LIMIT 1").fetchone()["code"]
            gold_before = conn.execute("SELECT gold FROM player WHERE id = 1").fetchone()["gold"]
        world.apply_turn(_turn("Carter nods. \"Then we leave at dawn.\""), "I'll take the job.")
        with db.connect() as conn:
            self.assertEqual(conn.execute("SELECT status FROM quests WHERE code = ?", (code,)).fetchone()["status"], "active")
        done = "At the western border the guards count the bolts of silk and Carter pays you the forty silver."
        state = world.apply_turn(
            _turn(done, quest_changes={"updates": [{"quest": code, "action": "complete", "evidence": "Carter pays you the forty silver"}]}),
            "Hand over the silk",
        )
        self.assertEqual(state["quest_report"]["updated"], [{"code": code, "action": "complete"}])
        with db.connect() as conn:
            row = conn.execute("SELECT status FROM quests WHERE code = ?", (code,)).fetchone()
            gold_after = conn.execute("SELECT gold FROM player WHERE id = 1").fetchone()["gold"]
        self.assertEqual(row["status"], "completed")
        self.assertGreaterEqual(gold_after - gold_before, 40)

    def test_a_rejected_proposal_is_reported_not_created(self):
        changes = qp.parse_reply(CANNED_SILK_REPLY)
        changes["new"][0]["evidence"] = "words nobody said"
        state = world.apply_turn(_turn(SILK, quest_changes=changes), "Talk to the carter")
        self.assertEqual(state["quest_report"]["status"], "rejected")
        self.assertEqual(state["quest_report"]["created"], [])
        with db.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) AS c FROM quests WHERE notes LIKE 'parser:%'").fetchone()["c"], 0)

    def test_a_narrator_mark_alone_creates_the_quest(self):
        marks = [{"op": "QUEST", "title": "Escort the silk west", "giver": "Carter", "step": "Escort the silk", "evidence": "escorting a shipment of silk"}]
        state = world.apply_turn(_turn(SILK, quest_marks=marks), "Talk to the carter")
        self.assertEqual(state["quest_report"]["source"], "marks")
        self.assertEqual(len(state["quest_report"]["created"]), 1)

    def test_quests_off_means_nothing_is_created(self):
        with db.connect() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = 'playthrough_options'").fetchone()
            options = json.loads(row["value"])
            options["quests_enabled"] = False
            conn.execute("UPDATE settings SET value = ? WHERE key = 'playthrough_options'", (json.dumps(options),))
        state = world.apply_turn(_turn(SILK, quest_changes=qp.parse_reply(CANNED_SILK_REPLY)), "Talk to the carter")
        self.assertEqual(state["quest_report"]["status"], "skipped")

    def test_a_quiet_turn_still_reports(self):
        state = world.apply_turn(_turn(SCENERY), "Look around")
        self.assertEqual(state["quest_report"]["status"], "skipped")


if __name__ == "__main__":
    unittest.main()
