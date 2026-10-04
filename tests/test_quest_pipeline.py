"""
The quest pipeline from the narrator to the turn the world applies.

The narrator may mark work with QUEST / QUEST_DONE; after the narration is
final, one small parser call proposes quests (app/quest_parser.py) and the
result rides the turn as quest_changes. These tests cover the DSL ops, the
handoff allowlists, and the hook in app/llm.py. The validation and the SQLite
side live with app/quest_parser.py and app/world.py.
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-quest-pipeline-test-"))
os.environ.update(
    {
        "AI_RPG_DB": str(_TMP / "world.db"),
        "AI_RPG_PACK_DIR": str(_TMP / "packs"),
        "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
        "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
        "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
        "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
    }
)

from app import llm, quest_parser  # noqa: E402
from app.prompts import _visible_world  # noqa: E402
from app.turn_dsl import parse_dsl_turn, parse_ops_detailed  # noqa: E402

NARRATION = (
    'The carter leans on the cart rail. "Get this silk to the western border and I will pay '
    'you twenty silver," he says, and you agree to meet him at dawn at the gate.'
)


def _dsl(ops: str) -> dict:
    return parse_dsl_turn(f"===NAR===\n{NARRATION}\n===OPS===\n{ops}\n")


class TestQuestOps(unittest.TestCase):
    def test_quest_parses_into_a_mark(self):
        turn = _dsl('QUEST "Escort the silk" GIVER A1 STEP "Meet the carter at the gate" AT "West Gate" REWARD "twenty silver"')
        self.assertEqual(
            turn["quest_marks"],
            [
                {
                    "op": "QUEST",
                    "title": "Escort the silk",
                    "giver": "A1",
                    "step": "Meet the carter at the gate",
                    "location": "West Gate",
                    "reward": "twenty silver",
                    "evidence": "",
                }
            ],
        )

    def test_quest_done_parses_with_its_action(self):
        turn = _dsl('QUEST_DONE Q3 accept\nQUEST_DONE "Find the well" complete')
        self.assertEqual(
            turn["quest_marks"],
            [
                {"op": "QUEST_DONE", "quest": "Q3", "action": "accept"},
                {"op": "QUEST_DONE", "quest": "Find the well", "action": "complete"},
            ],
        )

    def test_aliases_land_on_the_quest_ops(self):
        turn = _dsl('JOB "Clear the cellar" GIVER "Marta"\nOFFER "Carry word north"\nQUEST_UPDATE Q2 step_done')
        ops = [mark["op"] for mark in turn["quest_marks"]]
        self.assertEqual(ops, ["QUEST", "QUEST", "QUEST_DONE"])
        self.assertEqual(turn["quest_marks"][0]["giver"], "Marta")

    def test_a_bad_action_is_malformed_not_fatal(self):
        turn = _dsl('QUEST_DONE Q3 explode\nNOTE "the gate opens at dawn"')
        self.assertNotIn("quest_marks", turn)
        self.assertEqual(turn["_dsl"].get("malformed_ops"), 1)
        self.assertTrue(turn["journal"])

    def test_quest_flag_words_stay_ordinary_elsewhere(self):
        turn = _dsl("FOCUS event meeting at dawn")
        self.assertEqual(turn["scene_plan"]["focus_points"][0]["summary"], "meeting at dawn")

    def test_unknown_ops_are_reported(self):
        ops, skipped = parse_ops_detailed('NOTE "x"\nFROBNICATE the gate')
        self.assertEqual([op["op"] for op in ops], ["NOTE"])
        self.assertEqual(skipped, ["FROBNICATE the gate"])
        turn = _dsl('NOTE "x"\nFROBNICATE the gate')
        self.assertEqual(turn["_dsl"]["unknown_ops"], ["FROBNICATE the gate"])


class TestTheHandoffKeepsQuests(unittest.TestCase):
    def test_marks_and_changes_survive_the_turn_cleanup(self):
        turn = _dsl('QUEST "Escort the silk" GIVER A1 STEP "Meet at the gate"')
        turn["quest_changes"] = {"source": "parser", "new": [{"title": "Escort the silk"}], "updates": []}
        cleaned = llm._clean_turn_for_handoff(llm._normalize_turn(turn), "test")
        self.assertEqual(cleaned["quest_marks"][0]["title"], "Escort the silk")
        self.assertEqual(cleaned["quest_changes"]["new"][0]["title"], "Escort the silk")

    def test_active_quests_survive_the_context_handoff(self):
        self.assertIn("active_quests", llm.HANDOFF_BASE_CONTEXT_KEYS)
        context = {"active_quests": [{"code": "Q1", "title": "Find the well", "current_objective": "Ask the healer"}]}
        cleaned = llm._clean_context_for_handoff(context, "test")
        self.assertEqual(cleaned.get("active_quests"), context["active_quests"])

    def test_the_prompt_shows_active_quests_without_a_quest_word(self):
        context = {
            "active_quests": [{"code": "Q1", "title": "Find the well", "current_objective": "Ask the healer"}],
            "player": {},
        }
        world = _visible_world(context, "look around")
        self.assertEqual(world.get("active_quests"), [{"title": "Find the well", "code": "Q1", "now": "Ask the healer"}])

    def test_a_full_turn_verifier_reply_keeps_the_marks(self):
        draft = _dsl('QUEST "Escort the silk" GIVER A1 STEP "Meet at the gate"')
        verified = {"narration": NARRATION, "player": {}, "self_check": {"passed": True}}
        resolved = llm._resolve_verified_turn(verified, draft, {})
        self.assertEqual(resolved["quest_marks"][0]["title"], "Escort the silk")


class TestTheParserHook(unittest.TestCase):
    PROPOSAL = {"new": [{"title": "Escort the silk", "evidence": "Get this silk to the western border"}], "updates": []}

    def _turn(self):
        return {"narration": NARRATION, "quest_marks": [{"op": "QUEST", "title": "Escort the silk"}]}

    def _patched(self, **overrides):
        calls = {
            "needs_quest_parse": mock.Mock(return_value=True),
            "build_parser_prompt": mock.Mock(return_value=("s", "u")),
            "parse_reply": mock.Mock(return_value=dict(self.PROPOSAL)),
            "merge_marks": mock.Mock(side_effect=lambda parsed, marks: {**parsed, "source": "parser+marks"}),
        }
        calls.update(overrides)
        return mock.patch.multiple(quest_parser, **calls), calls

    def test_the_hook_sets_quest_changes_and_traces_the_call(self):
        patcher, calls = self._patched()
        trace: list = []
        with patcher, mock.patch.object(llm, "_chat_json", return_value={"new": []}) as chat:
            turn = llm._run_quest_parser(self._turn(), {"active_quests": []}, "I agree", trace=trace)
        self.assertEqual(turn["quest_changes"]["source"], "parser+marks")
        self.assertEqual(turn["quest_changes"]["new"][0]["title"], "Escort the silk")
        self.assertEqual(chat.call_args.kwargs["phase"], quest_parser.PARSER_PHASE)
        self.assertEqual(chat.call_args.kwargs["max_tokens"], quest_parser.PARSER_MAX_TOKENS)
        record = [r for r in trace if r.get("phase") == quest_parser.PARSER_PHASE][-1]
        self.assertEqual(record["event"], "parsed")
        self.assertTrue(record["gate"])

    def test_a_closed_gate_makes_no_model_call(self):
        patcher, _calls = self._patched(
            needs_quest_parse=mock.Mock(return_value=False),
            merge_marks=mock.Mock(return_value={"new": [], "updates": [], "source": "marks"}),
        )
        with patcher, mock.patch.object(llm, "_chat_json") as chat:
            turn = llm._run_quest_parser({"narration": "Rain."}, {}, "wait")
        chat.assert_not_called()
        self.assertNotIn("quest_changes", turn)

    def test_a_model_failure_keeps_the_marks(self):
        merged = {"new": [{"title": "Escort the silk"}], "updates": [], "source": "marks"}
        patcher, calls = self._patched(merge_marks=mock.Mock(return_value=merged))
        trace: list = []
        with patcher, mock.patch.object(llm, "_chat_json", side_effect=llm.LlmError("timed out")):
            turn = llm._run_quest_parser(self._turn(), {}, "I agree", trace=trace)
        self.assertEqual(turn["quest_changes"], merged)
        self.assertEqual(calls["merge_marks"].call_args.args[0], {"new": [], "updates": []})
        self.assertEqual(trace[-1]["event"], "model_failed")

    def test_an_unready_parser_never_breaks_the_turn(self):
        patcher, _calls = self._patched(needs_quest_parse=mock.Mock(side_effect=NotImplementedError))
        trace: list = []
        with patcher, mock.patch.object(llm, "_chat_json") as chat:
            turn = llm._run_quest_parser(self._turn(), {}, "I agree", trace=trace)
        chat.assert_not_called()
        self.assertEqual(turn["narration"], NARRATION)
        self.assertEqual(trace[-1]["event"], "error")

    def test_the_kill_switch_skips_the_model(self):
        patcher, _calls = self._patched(merge_marks=mock.Mock(return_value={"new": [{"title": "x"}], "updates": []}))
        with patcher, mock.patch.dict(os.environ, {"AI_RPG_QUEST_PARSER": "0"}), mock.patch.object(llm, "_chat_json") as chat:
            turn = llm._run_quest_parser(self._turn(), {}, "I agree")
        chat.assert_not_called()
        self.assertEqual(turn["quest_changes"]["new"][0]["title"], "x")

    def test_parser_inputs_come_from_the_location_tree(self):
        context = {
            "current_location": {"code": "L1", "name": "Market"},
            "locations": [{"code": "L1", "name": "Market", "npcs": [{"code": "A1", "name": "Carter", "role": "carter"}]}],
            "open_offers": [{"code": "Q9", "title": "A parcel to carry"}],
        }
        inputs = llm._quest_parser_inputs(context)
        self.assertEqual(inputs["npcs"], [{"code": "A1", "name": "Carter", "role": "carter"}])
        self.assertEqual(inputs["locations"], [{"code": "L1", "name": "Market"}])
        self.assertEqual(inputs["open_offers"][0]["code"], "Q9")


if __name__ == "__main__":
    unittest.main()
