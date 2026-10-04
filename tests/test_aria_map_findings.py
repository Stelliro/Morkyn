"""
Regressions from a two-turn game: Aria "handed over" a map, then asked to be
paid for it.

* The opening's ops only introduced Aria; the depth retry grew the scene from
  470 to 2310 characters and added "Let me offer you a small map ... Take
  this", with no op behind it. No item, no map reveal.
* The fact check never ran: the DSL skip-verify setting skipped it at 0.47 and
  0.24 certainty, on a turn that granted and took an item.
* '"Twelve gold...' opened the reply three times (12 characters, under the
  45-character repeat floor).
* A map the player receives should reveal ground on their map, not take a slot.
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
_TMP = Path(tempfile.mkdtemp(prefix="morkyn-aria-"))
os.environ.update(
    {
        "AI_RPG_DB": str(_TMP / "world.db"),
        "AI_RPG_PACK_DIR": str(_TMP / "packs"),
        "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
        "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
        "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
    }
)

from app import llm, tile_world, world  # noqa: E402
from app.narration_pipeline import drop_repeated_sentences  # noqa: E402


class TestTheDepthRetryAddsNoEvents(unittest.TestCase):
    DRAFT = 'Aria approaches you. "Looking for a guide for your journey?" she asks.'

    def test_an_invented_handover_is_caught(self):
        expanded = self.DRAFT + ' "Let me offer you a small map," she says. "Take this," she says, handing it to you.'
        self.assertTrue(llm._expansion_adds_handover(self.DRAFT, expanded))

    def test_texture_alone_passes(self):
        expanded = self.DRAFT + " Spice smoke drifts between the stalls; somewhere a mule complains."
        self.assertEqual(llm._expansion_adds_handover(self.DRAFT, expanded), [])

    def test_a_handover_already_in_the_draft_is_not_new(self):
        draft = 'Aria hands you a folded map. "Take this," she says.'
        self.assertEqual(llm._expansion_adds_handover(draft, draft + " The leather is soft with age."), [])

    def test_the_rejected_expansion_keeps_the_short_scene(self):
        turn = {"narration": self.DRAFT, "scene_plan": {"goal": "talk"}}
        long_false = self.DRAFT + ' "Take this," she says, handing you a map. ' + "The hall is loud. " * 80

        with mock.patch.object(llm, "_retry_narration_prose", return_value={**turn, "narration": long_false}):
            trace: list = []
            out = llm._ensure_narration_depth(turn, {}, "", "sys", 30, [], "narration_depth_dsl_retry", trace)
        self.assertNotIn("Take this", out.get("narration", ""))
        self.assertTrue(any(e.get("event") == "depth_retry_rejected" for e in trace))


class TestTheSkipSettingSkipsOnlySafeTurns(unittest.TestCase):
    def test_low_certainty_or_risky_changes_are_checked(self):
        self.assertFalse(llm._dsl_turn_safe_to_skip({}, {"certainty": 0.24}))
        self.assertFalse(llm._dsl_turn_safe_to_skip({"inventory_changes": [{"name": "map"}]}, {"certainty": 0.95}))
        self.assertFalse(llm._dsl_turn_safe_to_skip({"quest_marks": [{"op": "QUEST"}]}, {"certainty": 0.95}))
        self.assertFalse(llm._dsl_turn_safe_to_skip({"player": {"gold_delta": -12}}, {"certainty": 0.95}))

    def test_a_confident_talk_turn_may_skip(self):
        self.assertTrue(llm._dsl_turn_safe_to_skip({"npcs": [{"name": "Aria"}]}, {"certainty": 0.8}))


class TestRepeatedSpeechFragments(unittest.TestCase):
    def test_a_restarted_reply_is_dropped(self):
        paras = [
            'Aria raises an eyebrow. "Twelve gold... It\'s a start, but the map is large."',
            'Aria considers the coins. "Twelve gold... It\'s a start, but not nearly enough," she says.',
            'Aria shifts her gaze. "Twelve gold... Nearby, a cartographer is measuring a map.',
        ]
        _kept, dropped = drop_repeated_sentences(paras)
        self.assertEqual(dropped, ['"Twelve gold...', '"Twelve gold...'])

    def test_a_complete_short_line_may_still_echo(self):
        _kept, dropped = drop_repeated_sentences(['"I know," he said.', 'She waits. "I know," he said.'])
        self.assertEqual(dropped, [])


class TestReceivedMapsRevealGround(unittest.TestCase):
    def test_maps_are_recognised_and_cases_are_not(self):
        self.assertTrue(world.is_chart_item_name("small leather-bound map"))
        self.assertTrue(world.is_chart_item_name("sea chart"))
        self.assertFalse(world.is_chart_item_name("map case"))
        self.assertFalse(world.is_chart_item_name("rope"))

    def test_the_size_of_the_map_sets_its_reach(self):
        self.assertEqual(world.chart_reveal_radius("map", "a detailed map of the region"), 24)
        self.assertEqual(world.chart_reveal_radius("small worn map"), 10)
        self.assertEqual(world.chart_reveal_radius("map"), 16)

    def test_a_gained_map_leaves_the_inventory_list(self):
        kept, charts = world._split_chart_items(
            [{"name": "map", "quantity_delta": 1}, {"name": "rope", "quantity_delta": 1}, {"name": "map", "quantity_delta": -1}]
        )
        self.assertEqual([c["name"] for c in charts], ["map"])
        self.assertEqual([c["name"] for c in kept], ["rope", "map"])

    def test_reveal_adds_tiles_towns_and_landmarks(self):
        chart = {
            "id": "m1",
            "width": 60,
            "height": 60,
            "player": {"x": 30, "y": 30},
            "visited": ["30,30"],
            "settlements_meta": [{"id": "s-near", "x": 36, "y": 30}, {"id": "s-far", "x": 2, "y": 2}],
            "landmarks": [{"id": "lm1", "x": 25, "y": 34, "name": "Old Watchtower"}],
        }
        with mock.patch.object(tile_world, "_rebuild_grid", return_value=None), mock.patch.object(tile_world, "_save_map_payload"):
            report = tile_world.reveal_chart_area(chart, radius=10, source="map:test")
        self.assertEqual(report["tiles_revealed"], 21 * 21 - 1)
        self.assertEqual(report["settlements_known"], 1)
        self.assertEqual(report["landmarks_known"], 1)
        self.assertIn("40,40", chart["visited"])
        self.assertNotIn("41,30", chart["visited"])


if __name__ == "__main__":
    unittest.main()
