"""`allow_fallback=False` reaches every turn Continue can play.

The browser posts `/api/continue` with `allow_fallback: false` so a dead model
opens the failsafe dialog instead of writing offline narration. The opening
turn and a forced world-event beat were played through helpers that did not
take the flag, so those turns silently fell back and a forced quest beat was
resolved by the offline narrator.

Run:  python -m unittest tests.test_continue_turn_failsafe
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-continue-failsafe-test-"))
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
from app.failsafe import FailsafeBlocked  # noqa: E402


def setUpModule():
    os.environ.update(_ENV)
    assert str(db.db_path()).startswith(str(_TMP)), db.db_path()
    db.init_db()


_DEAD = "llama.cpp server refused connection at http://127.0.0.1:8080/v1/chat/completions"


def _dead_model(*_args, **_kwargs):
    raise llm.LlmError(_DEAD)


def _fresh_world():
    db.init_db()
    world.start_playthrough({"player_name": "Ash", "start_location": "Low Gate", "special_ability_origin": "none"})


def _apply_one_turn():
    world.apply_turn(
        {
            "narration": " ".join(["You stand at the gate and wait."] * 10),
            "self_check": {"passed": True, "issues_found": [], "corrections_made": []},
            "turn_summary": "waited",
        },
        player_input="I wait",
    )


class TestContinueCarriesTheFailsafeFlag(unittest.TestCase):
    def _patched(self):
        return (
            mock.patch.object(llm, "_chat_text", side_effect=_dead_model),
            mock.patch.object(llm, "_chat_json", side_effect=_dead_model),
            mock.patch.object(llm, "_chat_content", side_effect=_dead_model),
        )

    def test_turn_zero_raises_instead_of_writing_an_offline_opening(self):
        _fresh_world()
        self.assertLessEqual(world._current_turn_number(), 0)
        a, b, c = self._patched()
        with a, b, c:
            with self.assertRaises(FailsafeBlocked):
                world.play_continue_turn(allow_fallback=False)
        self.assertLessEqual(world._current_turn_number(), 0, "no turn may be written when the model is down")

    def test_forced_world_event_raises_and_stays_unresolved(self):
        _fresh_world()
        _apply_one_turn()
        self.assertGreaterEqual(world._current_turn_number(), 1)
        event = world.queue_world_event(kind="quest_stage", summary="The gate opens.", force=True, due_turn=0)
        a, b, c = self._patched()
        with a, b, c:
            with self.assertRaises(FailsafeBlocked):
                world.play_continue_turn(allow_fallback=False)
        with db.connect() as conn:
            row = conn.execute("SELECT status FROM gm_events WHERE id = ?", (int(event["id"]),)).fetchone()
        self.assertNotEqual(str(row["status"]), "resolved", "a forced beat must not be resolved by the offline narrator")

    def test_default_still_falls_back(self):
        """The old behaviour stays for callers that did not ask to be told."""
        _fresh_world()
        a, b, c = self._patched()
        with a, b, c:
            payload = world.play_continue_turn()
        self.assertTrue(payload.get("used_fallback"))

    def test_helpers_accept_the_flag(self):
        import inspect

        self.assertIn("allow_fallback", inspect.signature(world.play_opening_turn).parameters)
        self.assertIn("allow_fallback", inspect.signature(world.play_world_event_turn).parameters)


def _scene_turn(narration: str) -> dict:
    return {
        "scene_plan": {"goal": "look", "focus_points": []},
        "narration_segments": [{"label": "scene", "text": narration}],
        "narration": narration,
        "player": {},
        "self_check": {"passed": True, "issues_found": [], "corrections_made": []},
        "turn_summary": "a beat",
        "scene_focus": "action",
    }


_SCENE = " ".join(["The yard is quiet and the rain keeps falling on the stones."] * 12)


def _play_live(player_input: str) -> dict:
    with mock.patch.object(world, "generate_turn", return_value=_scene_turn(_SCENE)):
        return world.play_turn(player_input)


def _journal_inputs(turn: int) -> list[tuple[str, str]]:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT kind, content FROM journal WHERE turn = ? AND kind IN ('opening','player','continue','wait') ORDER BY id",
            (turn,),
        ).fetchall()
    return [(str(r["kind"]), str(r["content"])) for r in rows]


class TestRewriteAndWaitCarryTheFailsafeFlag(unittest.TestCase):
    """Rewrite (/api/regenerate) and Wait/Meditate/Sleep (/api/wait) used to
    call play_turn with the default flag, so with the model still down the
    'Rewrite once the model is back' path wrote another offline turn."""

    def _patched(self):
        return (
            mock.patch.object(llm, "_chat_text", side_effect=_dead_model),
            mock.patch.object(llm, "_chat_json", side_effect=_dead_model),
            mock.patch.object(llm, "_chat_content", side_effect=_dead_model),
        )

    def test_regenerate_raises_and_keeps_the_input_for_the_next_rewrite(self):
        _fresh_world()
        _play_live("I look at the gate")
        turn = world._current_turn_number()
        self.assertGreaterEqual(turn, 1)
        a, b, c = self._patched()
        with a, b, c:
            with self.assertRaises(FailsafeBlocked) as caught:
                world.regenerate_last_turn(allow_fallback=False)
        self.assertEqual(caught.exception.problem.get("pending_replay", {}).get("turn"), turn)
        # The rewind went through and no offline turn was written on top of it.
        self.assertEqual(world._current_turn_number(), turn - 1)
        self.assertEqual(_journal_inputs(turn), [])
        # The model is back: the next Rewrite replays the kept input at the
        # same turn number instead of rewinding a second turn.
        with mock.patch.object(world, "generate_turn", return_value=_scene_turn(_SCENE)):
            payload = world.regenerate_last_turn(allow_fallback=False)
        self.assertTrue(payload.get("regenerated"))
        self.assertEqual(payload.get("regenerated_turn"), turn)
        self.assertEqual(world._current_turn_number(), turn)
        self.assertEqual(_journal_inputs(turn), [("player", "I look at the gate")])
        with db.connect() as conn:
            self.assertIsNone(world._read_pending_regeneration(conn), "a replayed input is consumed")

    def test_a_new_action_after_a_refused_rewrite_drops_the_kept_input(self):
        _fresh_world()
        _play_live("I look at the gate")
        turn = world._current_turn_number()
        a, b, c = self._patched()
        with a, b, c:
            with self.assertRaises(FailsafeBlocked):
                world.regenerate_last_turn(allow_fallback=False)
        _play_live("I walk the other way")
        self.assertEqual(world._current_turn_number(), turn)
        with mock.patch.object(world, "generate_turn", return_value=_scene_turn(_SCENE)):
            payload = world.regenerate_last_turn()
        self.assertEqual(payload.get("regenerated_turn"), turn)
        self.assertEqual(_journal_inputs(turn), [("player", "I walk the other way")], "the stale input must not replay")

    def test_regenerate_default_still_falls_back(self):
        _fresh_world()
        _play_live("I look at the gate")
        a, b, c = self._patched()
        with a, b, c:
            payload = world.regenerate_last_turn()
        self.assertTrue(payload.get("used_fallback"))

    def test_wait_raises_and_puts_the_clock_back(self):
        _fresh_world()
        _play_live("I look at the gate")
        turn = world._current_turn_number()
        before = world.get_world_time()
        a, b, c = self._patched()
        with a, b, c:
            with self.assertRaises(FailsafeBlocked):
                world.play_wait_turn(60, kind="wait", allow_fallback=False)
        self.assertEqual(world._current_turn_number(), turn, "no wait turn may be written when the model is down")
        after = world.get_world_time()
        self.assertEqual((after["day"], after["minute"]), (before["day"], before["minute"]), "a refused wait costs no minutes")

    def test_wait_default_still_falls_back(self):
        _fresh_world()
        _play_live("I look at the gate")
        a, b, c = self._patched()
        with a, b, c:
            payload = world.play_wait_turn(60, kind="wait")
        self.assertTrue(payload.get("used_fallback"))

    def test_routes_and_models_carry_the_flag(self):
        import inspect

        from app import main as main_mod

        self.assertIn("allow_fallback", main_mod.WaitRequest.model_fields)
        self.assertIn("allow_fallback", main_mod.RegenerateRequest.model_fields)
        self.assertIn("allow_fallback", inspect.signature(world.play_wait_turn).parameters)
        self.assertIn("allow_fallback", inspect.signature(world.regenerate_last_turn).parameters)
        for route in ("api_wait", "api_regenerate"):
            src = inspect.getsource(getattr(main_mod, route))
            self.assertIn("FailsafeBlocked", src, f"{route} must map the failsafe to a 503 problem")


if __name__ == "__main__":
    unittest.main()
