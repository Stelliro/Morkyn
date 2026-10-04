"""
Regressions from the first live quest-parser run on Qwen3 8B.

* The prose-repair reply came back as "<think>\\nOkay, the user wants me to
  rewrite the given scene..." and that became the player's narration.
* The parser turned "the shipment is in the cellar" (said right after "no one
  is hiring") into an offered quest.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_TMP = Path(tempfile.mkdtemp(prefix="morkyn-quest-live-"))
os.environ.update(
    {
        "AI_RPG_DB": str(_TMP / "world.db"),
        "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
        "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
        "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
    }
)

from app import llm, quest_parser  # noqa: E402

INN = (
    'The innkeeper wipes the counter. "No one is hiring, friend. The shipment is in the cellar, that is all I know." '
    'Later a woman says: "If you bring my brother home from the mill, I will pay you in silver."'
)


class TestReasoningNeverReachesThePlayer(unittest.TestCase):
    def test_a_closed_block_is_removed(self):
        self.assertEqual(llm.strip_reasoning("<think>\nplanning\n</think>\nThe rain falls."), "The rain falls.")

    def test_an_unclosed_block_cut_by_the_cap_is_removed(self):
        self.assertEqual(llm.strip_reasoning("<think>\nOkay, the user wants me to rewrite the scene"), "")

    def test_plain_text_and_json_pass_through(self):
        self.assertEqual(llm.strip_reasoning('{"narration": "x"}'), '{"narration": "x"}')
        self.assertEqual(llm.strip_reasoning("You step inside."), "You step inside.")

    def test_every_provider_reply_is_stripped_and_qwen3_is_told_not_to_think(self):
        seen = {}

        def fake_dispatch(config, system, user, **kwargs):
            seen["user"] = user
            return "<think>hidden</think>Visible."

        original_dispatch, original_config = llm._chat_content_dispatch, llm.get_model_config
        llm._chat_content_dispatch = fake_dispatch
        llm.get_model_config = lambda: {"provider": "mle", "mle_model": r"D:\models\Qwen3-8B-Q4_K_M.gguf", "response_token_cap": 500, "response_token_hard_cap": 800}
        try:
            out = llm._chat_content_unlocked("sys", "write the scene")
        finally:
            llm._chat_content_dispatch, llm.get_model_config = original_dispatch, original_config
        self.assertEqual(out, "Visible.")
        self.assertTrue(seen["user"].endswith("/no_think"))


class TestAQuestNeedsAnOffer(unittest.TestCase):
    def test_a_refusal_and_a_bare_fact_are_not_offers(self):
        self.assertFalse(quest_parser.evidence_offers_work("The shipment is in the cellar", INN))
        self.assertFalse(quest_parser.evidence_offers_work("No one is hiring", INN))

    def test_a_paid_request_and_an_assignment_are(self):
        self.assertTrue(quest_parser.evidence_offers_work("bring my brother home from the mill", INN))
        text = "You've been tasked with escorting a shipment of silk from here to the western border."
        self.assertTrue(quest_parser.evidence_offers_work("tasked with escorting a shipment of silk", text))

    def test_the_player_taking_the_job_counts(self):
        self.assertTrue(quest_parser.evidence_offers_work("I'll take the job", "", "That sounds fair. I'll take the job."))

    def test_validation_rejects_a_grounded_non_offer(self):
        changes = {"new": [{"title": "Check the cellar shipment", "evidence": "The shipment is in the cellar", "steps": [{"title": "Go down"}]}], "updates": []}
        accepted, rejected = quest_parser.validate_quest_changes(changes, narration=INN, npcs=[], locations=[], existing=[])
        self.assertFalse(accepted.get("new"))
        self.assertIn("evidence_is_not_an_offer", rejected[0]["reasons"])

    def test_a_narrator_mark_is_trusted_as_an_offer(self):
        changes = {"new": [{"title": "Check the cellar shipment", "evidence": "The shipment is in the cellar", "steps": [{"title": "Go down"}], "_from_mark": True}], "updates": []}
        accepted, _rejected = quest_parser.validate_quest_changes(changes, narration=INN, npcs=[], locations=[], existing=[])
        self.assertEqual(len(accepted.get("new") or []), 1)



FERRY = (
    '"Not much," he grunts. "The riverfolk are still clearing the wreckage from the storm, and the '
    'ferryman\u2019s looking for a hand with the nets. But you\u2019ll have to talk to him yourself."'
)
DOCKS = 'Elara nods and hands you a small pouch of coins. "Start at the docks. The captain needs help loading cargo."'


class TestTheSecondLiveRun(unittest.TestCase):
    """Second Qwen3 8B run: the gate had become too strict."""

    def test_a_hand_wanted_and_help_needed_are_offers(self):
        self.assertTrue(quest_parser.evidence_offers_work("looking for a hand with the nets", FERRY))
        self.assertTrue(quest_parser.evidence_offers_work("The captain needs help loading cargo", DOCKS, "I'll take the job."))

    def test_a_giver_named_in_the_story_without_a_row_is_kept(self):
        changes = {
            "new": [{"title": "Help the ferryman with the nets", "giver": "the ferryman", "evidence": "looking for a hand with the nets", "steps": [{"title": "Find the ferryman"}]}],
            "updates": [],
        }
        accepted, rejected = quest_parser.validate_quest_changes(changes, narration=FERRY, npcs=[], locations=[], existing=[])
        self.assertEqual(len(accepted.get("new") or []), 1, rejected)
        self.assertEqual(accepted["new"][0]["giver_name"], "the ferryman")

    def test_a_giver_nobody_mentioned_is_still_refused(self):
        changes = {
            "new": [{"title": "Help the ferryman with the nets", "giver": "Lord Ashby", "evidence": "looking for a hand with the nets", "steps": [{"title": "Find him"}]}],
            "updates": [],
        }
        _accepted, rejected = quest_parser.validate_quest_changes(changes, narration=FERRY, npcs=[], locations=[], existing=[])
        self.assertIn("unknown_giver", rejected[0]["reasons"])

    def test_a_mark_matching_a_parser_title_keeps_its_trust(self):
        parsed = {"new": [{"title": "Captain's Load", "evidence": "Start at the docks", "steps": [{"title": "Go to the docks"}]}], "updates": []}
        merged = quest_parser.merge_marks(parsed, [{"op": "QUEST", "title": "Captain's Load", "giver": "", "step": "Go to the docks"}])
        self.assertTrue(merged["new"][0].get("_from_mark"))


if __name__ == "__main__":
    unittest.main()
