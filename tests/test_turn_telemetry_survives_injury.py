"""Every per-turn measurement survives play_turn's state refresh.

`apply_turn` annotates the state it returns with dice_rolls, movement,
map_walk, voice_check and gear_check. On a turn whose skill check produced an
injury, `play_turn` re-reads state from the database and re-attached only
three of the five, so map_walk and gear_check vanished from `payload.state`
exactly on those turns, and neither was ever at the payload top level the way
movement and voice_check are. One tuple now names the set on both sides.

Run:  python -m unittest tests.test_turn_telemetry_survives_injury
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-telemetry-test-"))
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

from app import db, rng, skill_checks, world  # noqa: E402


def setUpModule():
    os.environ.update(_ENV)
    assert str(db.db_path()).startswith(str(_TMP)), db.db_path()
    db.init_db()


def _fresh_world():
    db.init_db()
    rng.reset_seed_cache()
    world.start_playthrough(
        {
            "player_name": "Ash",
            "start_location": "Low Gate",
            "special_ability_origin": "none",
            "dice_checks_enabled": True,
        }
    )


_SCENE = " ".join(["You work the lock while the rain keeps falling on the stones."] * 12)


def _turn() -> dict:
    return {
        "scene_plan": {"goal": "look", "focus_points": []},
        "narration_segments": [{"label": "scene", "text": _SCENE}],
        "narration": _SCENE,
        "player": {},
        "self_check": {"passed": True, "issues_found": [], "corrections_made": []},
        "turn_summary": "a beat",
        "scene_focus": "action",
    }


_INJURY = {"limb": "hand", "health_delta": -2, "summary": "A split knuckle.", "severe": False, "combat_penalty": {}}


class TestTelemetrySurvivesTheInjuryRefresh(unittest.TestCase):
    def _play_with_injury(self) -> dict:
        real = skill_checks.resolve_check

        def injured(*args, **kwargs):
            out = real(*args, **kwargs)
            out["injury"] = dict(_INJURY)
            return out

        with mock.patch.object(skill_checks, "resolve_check", side_effect=injured):
            with mock.patch.object(world, "generate_turn", return_value=_turn()):
                return world.play_turn("I pick the lock on the gate")

    def test_every_listed_key_is_set_by_apply_turn(self):
        _fresh_world()
        state = world.apply_turn(_turn(), "I look around")
        for key in world.TURN_STATE_TELEMETRY_KEYS:
            if key == "dice_rolls":
                continue  # only present when the turn rolled a band
            self.assertIn(key, state, f"apply_turn must annotate {key}")

    def test_map_walk_and_gear_check_survive_an_injury_turn(self):
        _fresh_world()
        payload = self._play_with_injury()
        checks = payload.get("skill_checks") or []
        self.assertTrue(checks and checks[0].get("injury"), "the turn must have taken the injuries path")
        state = payload["state"]
        for key in ("movement", "voice_check", "map_walk", "gear_check"):
            self.assertIn(key, state, f"state.{key} was dropped by the post-injury refresh")
        self.assertIsInstance(state["map_walk"], dict)
        self.assertIn("status", state["map_walk"])
        self.assertIsInstance(state["gear_check"], dict)

    def test_map_walk_and_gear_check_ride_at_the_payload_top_level(self):
        _fresh_world()
        payload = self._play_with_injury()
        self.assertEqual(payload["map_walk"], payload["state"]["map_walk"])
        self.assertEqual(payload["gear_check"], payload["state"]["gear_check"])
        self.assertEqual(payload["movement"], payload["state"]["movement"])


if __name__ == "__main__":
    unittest.main()
