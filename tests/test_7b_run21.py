"""7B run 21 (Qwen2.5 7B on MLE, agent as player): the scene ends where the requested trip arrives."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-7b-run21-"))
_ENV = isolated_data_env(str(_TMP))
_SAVED_ENV: dict[str, str | None] = {}

LINE = ('"Well enough to know driftwood doesn\'t pay a debt." I head out onto the flats toward the drowned lower '
        "district, keeping the reckoner in my hand.")
PROSE = (
    "“Well enough to know driftwood doesn't pay a debt,” you say. You head out onto the driftwood-laden "
    "saltflats, the air cool and salty, the sun just rising over the horizon.\n\n"
    "You walk south, the mudflats stretching out before you. The day stretches on, and you find yourself at the "
    "edge of the lower district, the ruins of the old town now a shadow of its former self.\n\n"
    "The ruins are quiet, the streets empty. The salt-trees stand sentinel, their twisted branches reaching for the sky.\n\n"
    "You find a small, weathered driftwood cabin and rest there for a moment. You decide to head back to Saltmarrow. "
    "As you near the alehouse, you see Tilda Brewster sitting outside. You enter the alehouse and take a seat at the bar."
)


def setUpModule():
    _SAVED_ENV.update({key: os.environ.get(key) for key in _ENV})
    os.environ.update(_ENV)


def tearDownModule():
    for key, value in _SAVED_ENV.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


class SceneEndsWhereTheTripArrives(unittest.TestCase):
    def test_cut_after_arrival(self):
        from app import llm

        turn = {"narration": PROSE, "player": {"move_to_location": "Saltmarrow Alehouse"}}
        out = llm._cut_scene_after_completed_act(turn, LINE)
        self.assertTrue(out["narration"].endswith("reaching for the sky."), out["narration"][-200:])
        self.assertIn("edge of the lower district", out["narration"])
        self.assertNotIn("alehouse", out["narration"])
        self.assertEqual(out["_scene_cut"]["family"], "after_arrival")
        self.assertIsNone(out["player"]["move_to_location"])

    def test_no_arrival_no_cut(self):
        from app import llm

        prose = ("You head out onto the flats, the mud soft under your boots and the gulls loud overhead as the "
                 "light grows. The water is a thin line far off, and the ruins rise like broken teeth. "
                 "You decide to head back to Saltmarrow.")
        self.assertIsNone(llm._completion_cut_point(prose, LINE))

    def test_someone_speaks_first_no_cut(self):
        from app import llm

        prose = PROSE.replace(
            "The ruins are quiet, the streets empty.",
            'A fisher calls out, "You\'re out early, flat-runner?" The ruins are quiet.',
        )
        self.assertIsNone(llm._completion_cut_point(prose, LINE))

    def test_not_a_trip(self):
        from app import llm

        self.assertIsNone(llm._completion_cut_point(PROSE, '"How much for the rope?" I ask the chandler.'))


class TheWalkLandsWhereItArrives(unittest.TestCase):
    def test_lower_district(self):
        from app import llm, world
        from app.db import connect, init_db

        init_db()
        world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
        cut = llm._cut_scene_after_completed_act({"narration": PROSE, "player": {}}, LINE)
        with connect() as conn:
            result = {"narration": cut["narration"], "player": {}}
            world.resolve_movement(conn, result, LINE, intent="travel", narration=cut["narration"])
        self.assertEqual(result["player"].get("move_to_location"), "The Drowned Lower District")


if __name__ == "__main__":
    unittest.main()
