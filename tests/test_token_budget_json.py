"""JSON-aware token-budget pruning.

Every turn packet (`build_user_prompt`, `build_verify_prompt`,
`build_dsl_user_prompt`) is one JSON object. `enforce_token_budget` used to
shrink an over-budget packet by cutting text out of its middle and inserting a
marker, which handed the model an unparseable object. It now shortens long
`world_state` strings, then drops `world_state` keys in
`WORLD_STATE_DROP_ORDER`, re-serialising so the packet stays valid JSON, and
falls back to the middle cut only when that is not enough. Non-JSON prompts
keep the middle cut.

Run:  python -m unittest tests.test_token_budget_json
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-token-budget-json-test-"))
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

from app import llm  # noqa: E402


def setUpModule():
    os.environ.update(_ENV)


HIGH_PRIORITY = (
    "player",
    "current_location",
    "world_time",
    "turn",
    "movement_contract",
    "naming_contract",
    "recall_contract",
    "mechanics_context",
)
PACKET_FIELDS = ("instruction", "player_input", "turn_kind", "output_contract", "instructions")

_CONFIG = {"context_window": 32768, "response_token_cap": 1500, "response_token_hard_cap": 2000}


def _high_priority_world() -> dict:
    return {
        "world_time": {"day": 3, "hour": 14},
        "turn": 12,
        "player": {"name": "P", "code": "PC_1", "hp": 10, "worn": [{"name": "cloak", "code": "IT_1"}]},
        "current_location": {"name": "L", "code": "LOC_1", "people": [{"name": "N", "code": "NPC_1"}]},
        "movement_contract": {"travel_intent": False, "current_location": {"code": "LOC_1"}},
        "naming_contract": {"rule": "keep codes"},
        "recall_contract": {"rule": "recall only listed facts"},
        "mechanics_context": {"resolved_checks": [{"skill": "SK_1", "result": "pass"}]},
    }


def _huge_packet() -> dict:
    world = _high_priority_world()
    world["npc_psychology_context"] = "grudge " * 300
    world["named"] = [{"code": f"NPC_{i}", "name": f"n{i}", "description": "d" * 900} for i in range(40)]
    world["conversations"] = [{"with": f"NPC_{i}", "lines": ["x" * 200] * 5} for i in range(20)]
    world["open_offers"] = [{"title": f"t{i}", "source": "s"} for i in range(50)]
    world["settings"] = {"playthrough_options": {"choices": {"tone": "grim"}}}
    return {
        "world_state": world,
        "turn_kind": "scene",
        "player_input": "look around",
        "instruction": "Narrate the scene.",
        "output_contract": {"format": "nar_ops_v0"},
        "instructions": ["Fill ===NAR=== with prose."],
    }


class TestJsonAwarePruning(unittest.TestCase):
    def setUp(self):
        self._cfg = mock.patch.object(llm, "get_model_config", return_value=dict(_CONFIG))
        self._cfg.start()
        self.addCleanup(self._cfg.stop)

    def test_huge_packet_stays_valid_json_with_high_priority_keys(self):
        packet = _huge_packet()
        raw = json.dumps(packet, ensure_ascii=True, separators=(",", ":"))
        self.assertGreater(llm.estimated_tokens(raw), 3000)
        system, user, diag = llm.enforce_token_budget("sys", raw, max_input_tokens=3000, reserve_output_tokens=200)
        self.assertEqual(system, "sys")
        self.assertNotIn("truncated by enforce_token_budget", user)
        pruned = json.loads(user)
        self.assertTrue(diag["pruned"])
        self.assertTrue(diag["within_budget"], diag)
        self.assertLessEqual(llm.estimated_tokens("sys") + llm.estimated_tokens(user), 3000)
        for key in PACKET_FIELDS:
            self.assertEqual(pruned[key], packet[key], key)
        world = pruned["world_state"]
        for key in HIGH_PRIORITY:
            self.assertEqual(world[key], packet["world_state"][key], key)
            self.assertNotIn(key, diag["keys_dropped"])
        self.assertTrue(diag["keys_dropped"], diag)
        self.assertEqual(diag["truncated_chars"], len(raw) - len(user))
        for key in diag["keys_dropped"]:
            self.assertNotIn(key, world)

    def test_drop_order_follows_constant_and_low_keys_go_first(self):
        packet = _huge_packet()
        raw = json.dumps(packet, ensure_ascii=True, separators=(",", ":"))
        _, _, diag = llm.enforce_token_budget("sys", raw, max_input_tokens=3000, reserve_output_tokens=200)
        dropped = diag["keys_dropped"]
        ranks = [llm.WORLD_STATE_DROP_ORDER.index(key) for key in dropped]
        self.assertEqual(ranks, sorted(ranks), dropped)
        self.assertEqual(dropped[0], llm.WORLD_STATE_DROP_ORDER[0])
        # Every high-priority key sits at the tail of the order, after every other listed key.
        tail = llm.WORLD_STATE_DROP_ORDER[-len(HIGH_PRIORITY):]
        self.assertEqual(set(tail), set(HIGH_PRIORITY))

    def test_long_strings_shorten_before_any_key_drops(self):
        packet = _huge_packet()
        world = packet["world_state"]
        # Only one bulky thing: a single long string under a low-priority key.
        for key in ("named", "conversations", "open_offers", "settings"):
            world.pop(key)
        world["npc_psychology_context"] = "grudge " * 400
        raw = json.dumps(packet, ensure_ascii=True, separators=(",", ":"))
        self.assertGreater(llm.estimated_tokens(raw), 600)
        _, user, diag = llm.enforce_token_budget("sys", raw, max_input_tokens=600, reserve_output_tokens=100)
        pruned = json.loads(user)
        self.assertEqual(diag["keys_dropped"], [])
        self.assertGreaterEqual(diag["strings_shortened"], 1)
        self.assertLessEqual(len(pruned["world_state"]["npc_psychology_context"]), llm.WORLD_STATE_STRING_CAP + 1)
        self.assertTrue(diag["within_budget"], diag)
        for key in HIGH_PRIORITY:
            self.assertEqual(pruned["world_state"][key], packet["world_state"][key], key)

    def test_unknown_world_state_keys_drop_before_listed_ones(self):
        packet = _huge_packet()
        packet["world_state"]["future_block"] = [{"n": i} for i in range(400)]
        raw = json.dumps(packet, ensure_ascii=True, separators=(",", ":"))
        _, user, diag = llm.enforce_token_budget("sys", raw, max_input_tokens=3000, reserve_output_tokens=200)
        json.loads(user)
        self.assertEqual(diag["keys_dropped"][0], "future_block")

    def test_high_priority_keys_go_last_and_packet_fields_survive(self):
        packet = _huge_packet()
        # Not shortenable: many small rows under the most protected key.
        packet["world_state"]["player"]["inventory"] = [{"code": f"IT_{i}", "qty": 1} for i in range(800)]
        raw = json.dumps(packet, ensure_ascii=True, separators=(",", ":"))
        _, user, diag = llm.enforce_token_budget("sys", raw, max_input_tokens=1000, reserve_output_tokens=100)
        pruned = json.loads(user)
        self.assertNotIn("truncated by enforce_token_budget", user)
        self.assertEqual(diag["keys_dropped"][-1], "player")
        self.assertTrue(diag["within_budget"], diag)
        for key in PACKET_FIELDS:
            self.assertEqual(pruned[key], packet[key], key)

    def test_packet_fields_alone_over_budget_fall_back_to_middle_cut(self):
        packet = {"world_state": _high_priority_world(), "player_input": "A" * 20000, "instruction": "go"}
        raw = json.dumps(packet, ensure_ascii=True, separators=(",", ":"))
        _, user, diag = llm.enforce_token_budget("sys", raw, max_input_tokens=1500, reserve_output_tokens=100)
        self.assertIn("truncated by enforce_token_budget", user)
        self.assertTrue(diag["pruned"])
        self.assertTrue(diag["within_budget"], diag)
        # Every world_state key went, in order, before the cut was taken.
        self.assertEqual(diag["keys_dropped"], list(llm.WORLD_STATE_DROP_ORDER[-len(HIGH_PRIORITY):]))

    def test_non_json_prompt_keeps_middle_cut(self):
        huge = "A" * 50000
        system, user, diag = llm.enforce_token_budget("sys", huge, max_input_tokens=2000, reserve_output_tokens=200)
        self.assertLess(len(user), len(huge))
        self.assertIn("truncated by enforce_token_budget", user)
        self.assertTrue(diag["pruned"])
        self.assertTrue(diag["within_budget"])
        self.assertEqual(diag["keys_dropped"], [])
        self.assertEqual(diag["strings_shortened"], 0)

    def test_json_array_prompt_keeps_middle_cut(self):
        huge = json.dumps(["A" * 100] * 500)
        _, user, diag = llm.enforce_token_budget("sys", huge, max_input_tokens=2000, reserve_output_tokens=200)
        self.assertIn("truncated by enforce_token_budget", user)
        self.assertEqual(diag["keys_dropped"], [])

    def test_small_packet_is_untouched(self):
        packet = _huge_packet()
        raw = json.dumps(packet, ensure_ascii=True, separators=(",", ":"))
        system, user, diag = llm.enforce_token_budget("sys", raw, max_input_tokens=20000, reserve_output_tokens=200)
        self.assertEqual(user, raw)
        self.assertEqual(system, "sys")
        self.assertFalse(diag["pruned"])
        self.assertTrue(diag["within_budget"])
        self.assertEqual(diag["keys_dropped"], [])
        self.assertEqual(diag["strings_shortened"], 0)
        self.assertEqual(diag["truncated_chars"], 0)


if __name__ == "__main__":
    unittest.main()
