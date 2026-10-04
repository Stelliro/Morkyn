"""Shortcuts between the engine and the model: each one is a measured waste removed.

Measured on the 2026-10-03 traces (no GGUF path saved): the DSL draft failed
with a configuration error, the JSON draft was tried anyway, then the JSON
retry ran too. Three model calls, 24 seconds, for an error known before the
first call. On a real timeout the same path would wait the full draft timeout
twice. `_try_dsl_draft` now raises those errors instead of returning None.

Measured on the 2026-09-23 trace (grok-4.7): a verify pass overran its token
cap, came back as 5,224 characters ending mid-string, and the repair call that
followed spent 26 seconds returning the same characters with the quotes
closed. `_close_truncated_json` does that locally first.

Measured on the same trace: the four prose-only repair passes carried the full
JSON contract (~9.5k tokens) as their system prompt. They now carry
`PROSE_REPAIR_SYSTEM_PROMPT` (~1.1k), and the JSON depth fallback keeps the
JSON contract it actually needs.

Produced on every turn and dropped before the model: the server-rolled skill
checks (`mechanics_context.resolved_checks`), the narrator-only NPC psychology
block, and the per-action skill search. The system prompt has a rule for each.

Run:  python -m unittest tests.test_turn_pipeline_shortcuts
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-shortcuts-test-"))
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

from app import db, llm, world  # noqa: E402
from app.prompts import PROSE_REPAIR_SYSTEM_PROMPT, SYSTEM_PROMPT, build_user_prompt  # noqa: E402
from app.turn_dsl import build_dsl_user_prompt  # noqa: E402


def setUpModule():
    os.environ.update(_ENV)
    assert str(db.db_path()).startswith(str(_TMP)), db.db_path()
    db.init_db()


def _long_scene(words: int = 260) -> str:
    return " ".join(["You watch the rain cross the yard and wait."] * (words // 9))


# ---------------------------------------------------------------------------
# 1. A dead model is one failed call, not three
# ---------------------------------------------------------------------------
class TestDslDraftDoesNotFallThroughOnADeadModel(unittest.TestCase):
    def _run(self, text_error):
        text_calls = []
        json_calls = []

        def fake_text(*_args, **kwargs):
            text_calls.append(kwargs.get("phase"))
            raise llm.LlmError(text_error)

        def fake_json(*_args, **kwargs):
            json_calls.append(kwargs.get("phase"))
            raise llm.LlmError(text_error)

        with mock.patch.object(llm, "_chat_text", side_effect=fake_text), mock.patch.object(
            llm, "_chat_json", side_effect=fake_json
        ), mock.patch.object(llm, "draft_mode_enabled", return_value=True):
            with self.assertRaises(llm.LlmError) as caught:
                llm.generate_turn({"player": {"name": "Ash"}, "turn_plan": {"turn_kind": "player_action"}}, "I look around")
        return text_calls, json_calls, caught.exception

    def test_a_missing_gguf_path_is_raised_after_one_call(self):
        text_calls, json_calls, exc = self._run(
            "No GGUF model path is saved. Select a GGUF model file, save the model settings, then test again."
        )
        self.assertEqual(text_calls, ["draft_dsl"])
        self.assertEqual(json_calls, [], "the JSON draft and its retry must not run on a configuration error")
        self.assertIn("No GGUF model path", str(exc))

    def test_a_timeout_is_not_waited_for_twice(self):
        text_calls, json_calls, _ = self._run("draft_dsl timed out after 300s")
        self.assertEqual(text_calls, ["draft_dsl"])
        self.assertEqual(json_calls, [])

    def test_a_refused_connection_is_raised_once(self):
        text_calls, json_calls, _ = self._run("llama.cpp server refused connection at http://127.0.0.1:8080/v1/chat/completions")
        self.assertEqual(text_calls, ["draft_dsl"])
        self.assertEqual(json_calls, [])

    def test_the_trace_still_records_the_failed_draft(self):
        _, _, exc = self._run("No GGUF model path is saved.")
        phases = [(step.get("phase"), step.get("event")) for step in getattr(exc, "model_trace", [])]
        self.assertIn(("draft_dsl", "failed"), phases)

    def test_an_unreadable_answer_still_falls_back_to_the_json_draft(self):
        """The JSON fallback is for a model that answered badly, and it stays."""
        json_calls = []
        scene = _long_scene()

        def fake_json(*_args, **kwargs):
            json_calls.append(kwargs.get("phase"))
            return {
                "scene_plan": {"goal": "look", "focus_points": [{"kind": "scene", "summary": "yard"}]},
                "narration_segments": [{"label": "scene", "text": scene}],
                "player": {},
                "self_check": {"passed": True, "issues_found": [], "corrections_made": []},
                "turn_summary": "looked",
                "scene_focus": "action",
            }

        # An empty reply has no narration to transcode and nothing to salvage.
        with mock.patch.object(llm, "_chat_text", return_value=""), mock.patch.object(
            llm, "_chat_json", side_effect=fake_json
        ), mock.patch.object(llm, "draft_mode_enabled", return_value=True):
            result = llm.generate_turn({"player": {"name": "Ash"}, "turn_plan": {"turn_kind": "player_action"}}, "I look around")
        self.assertIn("draft", json_calls)
        self.assertTrue(str(result.get("narration") or "").startswith("You watch"))

    def test_a_generic_model_error_still_returns_none_from_the_dsl_helper(self):
        # Kept from tests/test_mle_provider.py: an unclassified failure is not a dead model.
        with mock.patch.object(llm, "_chat_text", side_effect=llm.LlmError("stop")), mock.patch.object(
            llm, "build_dsl_user_prompt", return_value="prompt"
        ), mock.patch.object(llm, "draft_mode_enabled", return_value=True):
            self.assertIsNone(llm._try_dsl_draft({}, "look", 30, [], []))

    def test_the_cleaned_context_is_built_once_per_turn(self):
        trace = []
        with mock.patch.object(llm, "_chat_text", return_value="no markers"), mock.patch.object(
            llm, "draft_mode_enabled", return_value=True
        ):
            cleaned = llm._clean_context_for_handoff({"player": {"name": "Ash"}}, "planner_to_draft", trace)
            llm._try_dsl_draft({"player": {"name": "Ash"}}, "look", 30, [], trace, active_context=cleaned)
        cleanups = [step for step in trace if step.get("event") == "handoff_context_cleanup"]
        self.assertEqual([step["phase"] for step in cleanups], ["planner_to_draft"])


class TestModelUnavailableClassifier(unittest.TestCase):
    def test_configuration_and_transport_failures_count(self):
        for text in (
            "No GGUF model path is saved.",
            "Saved GGUF model file was not found: D:/x.gguf",
            "MLE has no model loaded (qwen3:8b).",
            "MLE could not load D:/x.gguf. context 32768: boom",
            "OpenAI-compatible provider needs an API key.",
            "timed out after 300s",
            "[WinError 10061] No connection could be made",
        ):
            self.assertTrue(llm._is_model_unavailable_error(llm.LlmError(text)), text)

    def test_an_answer_that_was_merely_bad_does_not(self):
        for text in ("HTTP 500: boom", "Malformed JSON", "stop", "verify returned an empty chat completion."):
            self.assertFalse(llm._is_model_unavailable_error(llm.LlmError(text)), text)


# ---------------------------------------------------------------------------
# 2. Truncated JSON is closed locally
# ---------------------------------------------------------------------------
_TURN = {
    "scene_plan": {"goal": "Learn whether day-labor still hires", "focus_points": [{"kind": "scene", "summary": "track"}]},
    "narration_segments": [{"label": "scene", "text": 'You step out of the press of "shoulders" and catch Nettlelane [[B]].'}],
    "player": {"xp_delta": 150, "gold_delta": 0},
    "npcs": [{"name": "Ash", "code": "A", "role": "groom"}],
    "self_check": {"passed": True, "issues_found": []},
    "turn_summary": "asked about work",
}
_TEXT = json.dumps(_TURN)


class TestTruncatedJsonIsClosedLocally(unittest.TestCase):
    def test_a_cut_inside_a_string_keeps_the_prose_so_far(self):
        cut = _TEXT.index("Nettlelane") + 6
        parsed = llm._close_truncated_json(_TEXT[:cut])
        self.assertIsNotNone(parsed)
        self.assertTrue(parsed["narration_segments"][0]["text"].endswith("Nettle"))
        self.assertEqual(parsed["scene_plan"]["goal"], "Learn whether day-labor still hires")

    def test_a_cut_inside_a_number_drops_that_field_instead_of_clipping_it(self):
        cut = _TEXT.index('"xp_delta": 150') + len('"xp_delta": 15')
        parsed = llm._close_truncated_json(_TEXT[:cut])
        self.assertIsNotNone(parsed)
        self.assertNotIn("xp_delta", parsed.get("player") or {}, "15 is not 150")
        self.assertIn("scene_plan", parsed)

    def test_a_cut_after_a_key_drops_the_valueless_key(self):
        cut = _TEXT.index('"npcs":') + len('"npcs":')
        parsed = llm._close_truncated_json(_TEXT[:cut])
        self.assertIsNotNone(parsed)
        self.assertNotIn("npcs", parsed)
        self.assertEqual(parsed["player"], {"xp_delta": 150, "gold_delta": 0})

    def test_every_cut_point_past_the_first_value_parses(self):
        first_value_end = _TEXT.index('hires"') + len('hires"')
        failures = [cut for cut in range(first_value_end, len(_TEXT)) if llm._close_truncated_json(_TEXT[:cut]) is None]
        self.assertEqual(failures, [])

    def test_text_with_no_object_is_left_to_the_model(self):
        self.assertIsNone(llm._close_truncated_json("the model wrote prose instead"))
        self.assertIsNone(llm._close_truncated_json("{"))

    def test_complete_json_is_untouched(self):
        self.assertEqual(llm._extract_json(_TEXT), _TURN)

    def test_the_model_repair_call_is_not_made_for_a_capped_reply(self):
        calls = []

        def fake(*_args, **kwargs):
            calls.append(1)
            return _TEXT[: len(_TEXT) - 40]

        with mock.patch.object(llm, "_chat_content", side_effect=fake):
            parsed = llm._chat_json("system", "user")
        self.assertEqual(len(calls), 1, "a second call means the repair ran")
        self.assertEqual(parsed["scene_plan"]["goal"], _TURN["scene_plan"]["goal"])

    def test_garbage_still_reaches_the_model_repair(self):
        calls = []

        def fake(*_args, **kwargs):
            calls.append(1)
            return "not json" if len(calls) == 1 else '{"ok": true}'

        with mock.patch.object(llm, "_chat_content", side_effect=fake):
            parsed = llm._chat_json("system", "user")
        self.assertEqual(len(calls), 2)
        self.assertEqual(parsed, {"ok": True})


# ---------------------------------------------------------------------------
# 3. Prose repairs carry the prose contract; the JSON fallback keeps the JSON one
# ---------------------------------------------------------------------------
class TestProseRepairsUseTheProseContract(unittest.TestCase):
    def _short_turn(self):
        return {
            "scene_plan": {"goal": "g", "focus_points": []},
            "narration_segments": [{"label": "scene", "text": "You stand in the yard. Rain falls."}],
            "player": {},
            "self_check": {"passed": True, "issues_found": [], "corrections_made": []},
        }

    def test_the_depth_prose_retry_gets_the_prose_contract(self):
        seen = {}

        def fake_text(system_prompt, *_args, **kwargs):
            seen["system"] = system_prompt
            return _long_scene()

        with mock.patch.object(llm, "_chat_text", side_effect=fake_text), mock.patch.object(llm, "pipeline_enabled", return_value=False):
            out = llm._ensure_narration_quality(
                self._short_turn(), {}, "I look around", "JSON-CONTRACT", 30, [], "depth", [], prose_system_prompt="PROSE-CONTRACT"
            )
        self.assertEqual(seen["system"], "PROSE-CONTRACT")
        self.assertGreater(len(out["narration"]), 1000)

    def test_the_json_depth_fallback_keeps_the_json_contract(self):
        seen = {}

        def fake_json(system_prompt, *_args, **kwargs):
            seen["system"] = system_prompt
            return {
                "narration_segments": [{"label": "scene", "text": _long_scene()}],
                "self_check": {"passed": True, "issues_found": []},
                "scene_plan": {"goal": "g", "focus_points": []},
            }

        with mock.patch.object(llm, "_chat_text", side_effect=llm.LlmError("prose failed")), mock.patch.object(
            llm, "_chat_json", side_effect=fake_json
        ), mock.patch.object(llm, "pipeline_enabled", return_value=False):
            llm._ensure_narration_quality(
                self._short_turn(), {}, "I look around", "JSON-CONTRACT", 30, [], "depth", [], prose_system_prompt="PROSE-CONTRACT"
            )
        self.assertEqual(seen["system"], "JSON-CONTRACT")

    def test_without_a_prose_contract_the_old_behaviour_stands(self):
        seen = {}

        def fake_text(system_prompt, *_args, **kwargs):
            seen["system"] = system_prompt
            return _long_scene()

        with mock.patch.object(llm, "_chat_text", side_effect=fake_text), mock.patch.object(llm, "pipeline_enabled", return_value=False):
            llm._ensure_narration_quality(self._short_turn(), {}, "I look around", "JSON-CONTRACT", 30, [], "depth", [])
        self.assertEqual(seen["system"], "JSON-CONTRACT")

    def test_the_turn_pipeline_hands_repairs_the_prose_contract(self):
        systems = []
        scene = "You stand in the yard. Rain falls on the stones."

        def fake_text(system_prompt, *_args, **kwargs):
            systems.append(system_prompt)
            if kwargs.get("phase") == "draft_dsl":
                return f"===NAR===\n{scene}\n===OPS===\n"
            return _long_scene()

        with mock.patch.object(llm, "_chat_text", side_effect=fake_text), mock.patch.object(
            llm, "_chat_json", return_value={"narration_segments": [{"text": scene}], "self_check": {"passed": True}}
        ), mock.patch.object(llm, "draft_mode_enabled", return_value=True), mock.patch.object(llm, "pipeline_enabled", return_value=False):
            llm.generate_turn({"player": {"name": "Ash"}, "turn_plan": {"turn_kind": "player_action"}}, "I look around")
        repair_systems = systems[1:]
        self.assertTrue(repair_systems, "the short draft should have triggered a depth repair")
        # On a local provider the repair prompt starts with the draft's own
        # prompt (one shared KV prefix per turn; tests/test_shared_prefix.py)
        # and carries the prose contract after it. Either way the JSON
        # contract is not sent to a call that was told not to return JSON.
        json_contract_rule = SYSTEM_PROMPT.split("\n")[2]
        self.assertIn("source of truth", json_contract_rule)
        for system in repair_systems:
            self.assertIn(PROSE_REPAIR_SYSTEM_PROMPT.split("\n", 1)[0], system, system[:80])
            self.assertTrue(system.endswith(PROSE_REPAIR_SYSTEM_PROMPT), system[-80:])
            self.assertNotIn(json_contract_rule, system)

    def test_the_prose_contract_is_an_order_of_magnitude_smaller(self):
        self.assertLess(llm.estimated_tokens(PROSE_REPAIR_SYSTEM_PROMPT) * 6, llm.estimated_tokens(SYSTEM_PROMPT))


# ---------------------------------------------------------------------------
# 4. What the rules cite under mechanics_context actually ships
# ---------------------------------------------------------------------------
def _mechanics_context():
    return {
        "world_time": {"day": 1, "hour": 9, "label": "Day 1 - 09:00"},
        "player": {"name": "Ash"},
        "current_location": {"name": "Saltcut", "code": "L2", "id": 2},
        "mechanics_context": {
            "weather": {"kind": "rain", "label": "Steady rain", "strength": 0.4},
            "combat": {"status": "not_combat"},
            "resolved_checks": [
                {
                    "skill": {"code": "persuasion", "name": "Persuasion"},
                    "outcome": "failure",
                    "degree": "clear failure",
                    "natural": 4,
                    "total": 7,
                    "dc": 14,
                    "social_attitude": "Dismissive",
                    "social_direction": "NPC reaction lean: Dismissive. Honor traits.",
                }
            ],
            "social_attitudes": [{"skill": "persuasion", "outcome": "failure", "attitude": "Dismissive"}],
            "action_spend": {"ok": False, "blocked": True, "kind": "physical", "reasons": ["exhausted"], "delta": {}},
            "collapse": {"state": "staggering"},
            "area_reputation": -30,
            "social_reputation": {"flavor": "walked away", "npc_code": "B", "walked_away": True},
            "player_inventory_codes": ["I1", "I2"],
            "player_inventory_truncated": True,
            "ability_use": {"ok": False, "blocked": True, "ability": {"name": "Hearth Spark", "code": "AB1"}, "reasons": ["cooldown"]},
            "forced_events": [{"kind": "quest_force", "summary": "The portal opens."}],
        },
    }


class TestMechanicsReachThePacket(unittest.TestCase):
    def test_the_rolled_check_and_its_attitude_reach_both_prompts(self):
        context = _mechanics_context()
        for packet in (build_user_prompt(context, "I ask the groom for work"), build_dsl_user_prompt(context, "I ask the groom for work")):
            world_state = json.loads(packet)["world_state"]
            checks = world_state["mechanics_context"]["resolved_checks"]
            self.assertEqual(checks[0]["skill"], "persuasion")
            self.assertEqual(checks[0]["outcome"], "failure")
            self.assertEqual(checks[0]["attitude"], "Dismissive")
            self.assertNotIn("natural", checks[0], "the roll math stays server-side")
            self.assertIn("those dice already fell", json.loads(packet)["instruction"])

    def test_the_other_cited_mechanics_keys_reach_the_packet(self):
        mechanics = json.loads(build_user_prompt(_mechanics_context(), "I push on"))["world_state"]["mechanics_context"]
        self.assertTrue(mechanics["action_spend"]["blocked"])
        self.assertEqual(mechanics["collapse"], {"state": "staggering"})
        self.assertEqual(mechanics["area_reputation"], -30)
        self.assertEqual(mechanics["social_reputation"]["npc_code"], "B")
        self.assertEqual(mechanics["player_inventory_codes"], ["I1", "I2"])
        self.assertTrue(mechanics["player_inventory_truncated"])

    def test_a_quiet_turn_ships_none_of_them(self):
        context = _mechanics_context()
        context["mechanics_context"] = {"weather": {"kind": "clear", "label": "Clear"}, "combat": {"status": "not_combat"}, "area_reputation": 0}
        mechanics = json.loads(build_user_prompt(context, "I look"))["world_state"]["mechanics_context"]
        for key in ("resolved_checks", "action_spend", "collapse", "area_reputation", "social_reputation", "player_inventory_codes"):
            self.assertNotIn(key, mechanics)

    def test_every_mechanics_key_the_rules_cite_is_either_shipped_or_excused(self):
        import re

        from app import prompts

        cited = set(re.findall(r"mechanics_context\.([a-z_]+)", (ROOT / "app" / "prompts.py").read_text(encoding="utf-8")))
        shipped = set(prompts._mechanics_view(_mechanics_context()).keys())
        # `resources` is nested under player state and the blocked/collapse
        # signals already carry its consequence; `combat` ships when combat is on.
        excused = {"resources", "combat"}
        self.assertEqual(sorted(cited - shipped - excused), [], "cited by a rule, never shipped")


# ---------------------------------------------------------------------------
# 5. Narrator-only psychology and the per-action skill list reach the model
# ---------------------------------------------------------------------------
class TestLateContextKeysReachTheModel(unittest.TestCase):
    def test_the_psychology_block_survives_the_filter_and_lands_in_both_prompts(self):
        block = "[PRIVATE — narrator only]\nAldric harbours intense resentment toward the player."
        cleaned = llm._clean_context_for_handoff(
            {"player": {"name": "Ash"}, "turn_plan": {"turn_kind": "player_action"}, "npc_psychology_context": block},
            "planner_to_draft",
        )
        self.assertEqual(cleaned.get("npc_psychology_context"), block)
        for packet in (build_user_prompt(cleaned, "I greet Aldric"), build_dsl_user_prompt(cleaned, "I greet Aldric")):
            self.assertIn("harbours intense resentment", packet)
            self.assertIn("private narrator knowledge", json.loads(packet)["instruction"])

    def test_the_skill_search_result_reaches_the_packet_only_while_checks_are_on(self):
        on = {
            "player": {"name": "Ash"},
            "turn_plan": {"turn_kind": "player_action"},
            "skill_check_context": {
                "dice_checks_enabled": True,
                "active_skills": [{"code": "smithing", "name": "Smithing", "base_dc": 12}, {"code": "general", "name": "General"}],
                "rules": ["long rule text that must not ship"],
            },
        }
        packet = json.loads(build_user_prompt(llm._clean_context_for_handoff(on, "planner_to_draft"), "I hammer the blade"))
        self.assertEqual(packet["world_state"]["skill_check_context"], {"active_skills": [{"code": "smithing", "name": "Smithing"}, {"code": "general", "name": "General"}]})
        self.assertNotIn("must not ship", json.dumps(packet))
        off = dict(on, skill_check_context={"dice_checks_enabled": False})
        packet = json.loads(build_user_prompt(llm._clean_context_for_handoff(off, "planner_to_draft"), "I hammer the blade"))
        self.assertNotIn("skill_check_context", packet["world_state"])


# ---------------------------------------------------------------------------
# 6. Character art is not state payload twice, and never prompt material
# ---------------------------------------------------------------------------
class TestArtIsNotCarriedTwice(unittest.TestCase):
    def setUp(self):
        self.face = json.dumps({"data_url": "data:image/png;base64,FACE", "kind": "face"})
        self.body = json.dumps({"data_url": "data:image/png;base64,BODY", "kind": "fullbody"})
        with db.connect() as conn:
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('player_portrait', ?)", (self.face,))
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('player_fullbody', ?)", (self.body,))

    def tearDown(self):
        with db.connect() as conn:
            conn.execute("DELETE FROM settings WHERE key IN ('player_portrait', 'player_fullbody')")

    def test_state_names_the_art_once_at_the_top_level_and_never_carries_it(self):
        state = world.get_state()
        self.assertEqual((state.get("player_portrait") or {}).get("kind"), "face")
        self.assertEqual((state.get("player_fullbody") or {}).get("kind"), "fullbody")
        self.assertNotIn("player_portrait", state["settings"])
        self.assertNotIn("player_fullbody", state["settings"])
        self.assertEqual(json.dumps(state).count("base64,"), 0)

    def test_the_planner_packet_carries_no_art(self):
        packet = world.build_prompt_context(world.get_state(include_hidden=True), "I look around")
        self.assertNotIn("player_portrait", packet)
        self.assertNotIn("player_fullbody", packet)
        self.assertNotIn("base64,", json.dumps(packet, default=str))


# ---------------------------------------------------------------------------
# 7. The repair note is written once
# ---------------------------------------------------------------------------
class TestRepairNoteIsNotRepeated(unittest.TestCase):
    def test_three_normalize_passes_leave_one_note(self):
        turn = {
            "narration_segments": [{"label": "scene", "text": "You nod to Ash [[A]]."}],
            "self_check": {"passed": True, "issues_found": [], "corrections_made": []},
        }
        for _ in range(3):
            turn = llm._normalize_turn(turn, {})
        notes = [c for c in turn["self_check"]["corrections_made"] if c.startswith("Deterministic entity name/code repair")]
        self.assertEqual(len(notes), 1)


if __name__ == "__main__":
    unittest.main()
