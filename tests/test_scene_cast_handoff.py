"""The DSL CAST op reaches the world, and the DSL meta reaches the trace.

`CAST` is the only way the model changes who is in the active scene, and the
transcoder wrote `scene_cast` on every DSL turn. `_clean_turn_for_handoff`
rebuilds the turn from `TURN_SHAPE_ORDER`, which did not list `scene_cast`, so
every played turn reached `apply_turn` without it and `settings.active_scene`
was never written outside the debug cast command.

The same cleanup dropped `_dsl` (ops_count, malformed_ops) before the
`transcoded` trace entry read it, so the trace showed `ops_count: null` on
every DSL turn.

Run:  python -m unittest tests.test_scene_cast_handoff
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-scene-cast-test-"))
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
from app.turn_dsl import parse_dsl_turn  # noqa: E402


def setUpModule():
    os.environ.update(_ENV)
    assert str(db.db_path()).startswith(str(_TMP)), db.db_path()
    db.init_db()


_DSL_REPLY = (
    "===NAR===\n"
    + " ".join(["The gatekeeper steps out of the shadow and studies you without a word."] * 12)
    + "\n===OPS===\n"
    "CAST interacting B\n"
    "CAST keyword gate\n"
    "SUMMARY The gatekeeper notices you.\n"
)


class TestSceneCastSurvivesTheHandoff(unittest.TestCase):
    def test_cleanup_keeps_the_cast(self):
        turn = parse_dsl_turn(_DSL_REPLY, player_input="I approach the gate")
        self.assertEqual(turn["scene_cast"]["interacting"], ["B"])
        cleaned = llm._clean_turn_for_handoff(turn, "dsl_to_verify")
        self.assertEqual(cleaned["scene_cast"]["interacting"], ["B"])
        self.assertEqual(cleaned["scene_cast"]["keywords"], ["gate"])

    def test_scene_cast_is_in_both_allowlists(self):
        self.assertIn("scene_cast", llm.TURN_SHAPE_KEYS)
        self.assertIn("scene_cast", llm.TURN_SHAPE_ORDER)

    def test_apply_turn_writes_active_scene(self):
        db.init_db()
        world.start_playthrough({"player_name": "Ash", "start_location": "Low Gate", "special_ability_origin": "none"})
        with db.connect() as conn:
            # The cast names a real person standing here (app/conversation.py
            # keeps only those in the scene).
            loc = conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()[0]
            conn.execute("INSERT INTO npcs (code, location_id, name) VALUES ('B', ?, 'Gatekeeper')", (loc,))
        turn = parse_dsl_turn(_DSL_REPLY, player_input="I approach the gate")
        cleaned = llm._clean_turn_for_handoff(turn, "dsl_to_world")
        world.apply_turn(cleaned, player_input="I approach the gate")
        with db.connect() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = 'active_scene'").fetchone()
        self.assertIsNotNone(row, "settings.active_scene must be written from a played DSL turn")
        scene = json.loads(row["value"])
        self.assertIn("B", scene.get("interacting") or [])
        self.assertIn("B", scene.get("present") or [])
        self.assertIn("gate", scene.get("keywords") or [])


class TestDslMetaReachesTheTrace(unittest.TestCase):
    def _draft(self, reply: str):
        trace: list = []
        usage: list = []
        with mock.patch.object(llm, "_chat_text", return_value=reply), mock.patch.object(
            llm, "draft_mode_enabled", return_value=True
        ):
            turn = llm._try_dsl_draft({}, "I approach the gate", 30, usage, trace)
        return turn, trace

    def test_transcoded_entry_counts_ops_and_malformed_lines(self):
        reply = _DSL_REPLY + "NPC_NEW\n"  # NPC_NEW without a NAME is the malformed line
        turn, trace = self._draft(reply)
        self.assertIsNotNone(turn)
        entry = next(step for step in trace if step.get("phase") == "draft_dsl" and step.get("event") == "transcoded")
        self.assertEqual(entry.get("ops_count"), 4)
        self.assertEqual(entry.get("malformed_ops"), 1)
        self.assertEqual((turn.get("_dsl") or {}).get("malformed_ops"), 1)
        self.assertEqual((turn.get("_dsl") or {}).get("ops_count"), 4)

    def test_clean_turn_does_not_report_meta_as_removed(self):
        turn = parse_dsl_turn(_DSL_REPLY)
        trace: list = []
        llm._clean_turn_for_handoff(turn, "dsl_to_verify", trace)
        entry = next(step for step in trace if step.get("event") == "handoff_turn_cleanup")
        self.assertNotIn("_dsl", entry.get("removed_keys") or [])
        self.assertNotIn("scene_cast", entry.get("removed_keys") or [])

    def test_verifier_prompt_does_not_carry_engine_meta(self):
        draft = {"narration": "x", "_dsl": {"ops_count": 3}, "_narration_pipeline": {"budget": {}}}
        seen = llm._prompt_draft(draft)
        self.assertEqual(seen, {"narration": "x"})


if __name__ == "__main__":
    unittest.main()
