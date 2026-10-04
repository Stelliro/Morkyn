"""A dead model costs one timeout per turn, not one per prose pass.

Measured shape (llama_cpp, draft timeout 900s): the draft came back short, the
prose depth retry waited the full 900s and raised, and the whole-turn JSON
retry then waited the same 900s against the same hung server before the
unverified short draft went out. The voice, answer-act and recall passes each
had their own try/except and no shared signal, so each could add a further
timeout (or a managed llama.cpp restart wait) on top.

`_ensure_narration_depth` now stops its ladder on a model-unavailable error
and flags the usage row (`model_unavailable`); the prose passes that follow
read that flag and skip their call.

Run:  python -m unittest tests.test_dead_model_prose_passes
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-dead-model-test-"))
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


_CONTEXT = {"player": {"name": "Ash"}, "turn_plan": {"turn_kind": "player_action"}}


def _short_turn(chars: int = 700) -> dict:
    lines = [
        "You step into the yard and the wind pulls at your cloak.",
        "Mud has dried in ridges along the cart track, and a dog watches you from the gate.",
        "The baker's shutters are down, though the smell of bread still hangs in the cold air.",
        "A boy drags a bucket toward the well and does not look up.",
        "Somewhere behind the stables a hammer rings twice and stops.",
        "You count three doors on this side of the square, two of them barred.",
        "The guard at the far arch shifts his weight and looks your way.",
        "Your boots leave prints that the frost has not yet taken back.",
        "A sparrow lands on the trough, drinks, and goes.",
        "The sky over the roofs is the colour of old pewter.",
        "You can hear the river from here, low and steady under everything else.",
        "Nobody has asked your name yet.",
    ]
    scene = " ".join(lines)
    scene = (scene * (chars // len(scene) + 1))[:chars].rstrip()
    return {
        "scene_plan": {"goal": "look", "focus_points": [{"kind": "scene", "summary": "yard"}]},
        "narration_segments": [{"label": "scene", "text": scene}],
        "narration": scene,
        "player": {},
        "self_check": {"passed": True, "issues_found": [], "corrections_made": []},
        "turn_summary": "looked at the yard",
        "scene_focus": "action",
    }


def _failed_phases(usage: list[dict]) -> list[str]:
    return [str(entry.get("phase")) for entry in usage if str(entry.get("phase", "")).endswith("_failed")]


class TestDepthLadderStopsOnDeadModel(unittest.TestCase):
    def test_timeout_on_the_prose_retry_skips_the_json_retry(self):
        usage: list[dict] = []
        trace: list[dict] = []
        turn = _short_turn()
        with mock.patch.object(llm, "_chat_text", side_effect=llm.LlmError("timed out after 5s")), mock.patch.object(
            llm, "_chat_json"
        ) as chat_json:
            out = llm._ensure_narration_depth(turn, dict(_CONTEXT), "look", "sys", 5, usage, "narration_depth_retry", trace)
        chat_json.assert_not_called()
        self.assertEqual(_failed_phases(usage), ["narration_depth_retry_prose_failed"])
        self.assertTrue(usage[-1].get("model_unavailable"))
        self.assertEqual(
            out["narration"],
            llm._normalize_turn(_short_turn(), dict(_CONTEXT))["narration"],
            "the short draft goes out as it was",
        )
        events = [(entry.get("event"), entry.get("mode")) for entry in trace]
        self.assertIn(("depth_retry_failed", "prose"), events)
        self.assertIn(("depth_retry_skipped", "json"), events)

    def test_refused_connection_on_the_prose_retry_skips_the_json_retry(self):
        usage: list[dict] = []
        with mock.patch.object(
            llm, "_chat_text", side_effect=llm.LlmError("llama_cpp server refused connection at http://localhost:8080")
        ), mock.patch.object(llm, "_chat_json") as chat_json:
            llm._ensure_narration_depth(_short_turn(), dict(_CONTEXT), "look", "sys", 5, usage, "narration_depth_retry", [])
        chat_json.assert_not_called()
        self.assertTrue(llm._model_unavailable_noted(usage))

    def test_a_content_failure_still_falls_through_to_the_json_retry(self):
        """Only a dead model ends the ladder; thin prose keeps the JSON fallback."""
        usage: list[dict] = []
        with mock.patch.object(
            llm, "_chat_text", side_effect=llm.LlmError("Depth retry returned too little prose to trust.")
        ), mock.patch.object(llm, "_chat_json", side_effect=llm.LlmError("not json")) as chat_json:
            llm._ensure_narration_depth(_short_turn(), dict(_CONTEXT), "look", "sys", 5, usage, "narration_depth_retry", [])
        chat_json.assert_called_once()
        self.assertEqual(
            _failed_phases(usage),
            ["narration_depth_retry_prose_failed", "narration_depth_retry_json_failed"],
        )
        self.assertFalse(llm._model_unavailable_noted(usage))


class TestLaterPassesReadTheFlag(unittest.TestCase):
    def _drifting(self):
        return [
            mock.patch.object(llm, "_narration_voice_drift", return_value={"drift": True}),
            mock.patch.object(llm, "_answer_act_report", return_value={"unanswered": True, "topics": ["the key"]}),
            mock.patch.object(llm, "_recall_report", return_value={"missing": True, "specifics": ["Mara"]}),
        ]

    def test_voice_answer_and_recall_skip_once_the_model_is_flagged(self):
        usage: list[dict] = [{"phase": "narration_depth_retry_prose_failed", "error": "timed out after 5s", "model_unavailable": True}]
        trace: list[dict] = []
        turn = _short_turn()
        patches = self._drifting()
        for item in patches:
            item.start()
        try:
            with mock.patch.object(llm, "_chat_text") as chat_text:
                voiced = llm._ensure_narration_voice(turn, dict(_CONTEXT), "look", "sys", 5, usage, "narration_depth_retry", trace)
                answered = llm._ensure_answer_act(voiced, dict(_CONTEXT), "look", "sys", 5, usage, "narration_depth_retry", trace)
                llm._ensure_recall_specifics(answered, dict(_CONTEXT), "look", "sys", 5, usage, "narration_depth_retry", trace)
        finally:
            for item in patches:
                item.stop()
        chat_text.assert_not_called()
        events = [entry.get("event") for entry in trace]
        self.assertEqual(events, ["voice_retry_skipped", "answer_retry_skipped", "recall_retry_skipped"])

    def test_a_timeout_in_the_voice_pass_flags_the_rest(self):
        usage: list[dict] = []
        turn = _short_turn(1400)
        patches = self._drifting()
        for item in patches:
            item.start()
        try:
            with mock.patch.object(llm, "_chat_text", side_effect=llm.LlmError("timed out after 5s")) as chat_text:
                voiced = llm._ensure_narration_voice(turn, dict(_CONTEXT), "look", "sys", 5, usage, "narration_depth_retry", [])
                answered = llm._ensure_answer_act(voiced, dict(_CONTEXT), "look", "sys", 5, usage, "narration_depth_retry", [])
                llm._ensure_recall_specifics(answered, dict(_CONTEXT), "look", "sys", 5, usage, "narration_depth_retry", [])
        finally:
            for item in patches:
                item.stop()
        self.assertEqual(chat_text.call_count, 1, "the voice pass paid the one timeout; answer and recall did not")
        self.assertEqual(_failed_phases(usage), ["narration_depth_retry_voice_failed"])

    def test_whole_quality_pass_costs_one_timeout_on_a_dead_model(self):
        """End to end through _ensure_narration_quality with the pipeline off."""
        usage: list[dict] = []
        trace: list[dict] = []
        patches = self._drifting()
        for item in patches:
            item.start()
        try:
            with mock.patch.object(llm, "pipeline_enabled", return_value=False), mock.patch.object(
                llm, "_chat_text", side_effect=llm.LlmError("timed out after 5s")
            ) as chat_text, mock.patch.object(llm, "_chat_json") as chat_json:
                out = llm._ensure_narration_quality(
                    _short_turn(), dict(_CONTEXT), "look", "sys", 5, usage, "narration_depth_retry", trace
                )
        finally:
            for item in patches:
                item.stop()
        self.assertEqual(chat_text.call_count, 1)
        chat_json.assert_not_called()
        self.assertEqual(_failed_phases(usage), ["narration_depth_retry_prose_failed"])
        self.assertTrue(out.get("narration"))


if __name__ == "__main__":
    unittest.main()
