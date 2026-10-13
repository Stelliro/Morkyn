"""7B run 9 (Qwen2.5 7B on MLE, agent as player): the model's own XP and karma stand on something that happened."""
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-7b-run9-rewards-"))
_ENV = isolated_data_env(str(_TMP))
_SAVED_ENV: dict[str, str | None] = {}


def setUpModule():
    _SAVED_ENV.update({key: os.environ.get(key) for key in _ENV})
    os.environ.update(_ENV)


def tearDownModule():
    for key, value in _SAVED_ENV.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


T1_LINE = 'I walk over to the rag picker on the flats. "Hal, you look like you\'ve been out here since the last tide. Find anything worth the mud?"'
T1_PROSE = (
    "You walk over to the rag picker on the flatlands. Hal Garner, a rag picker, glances up from his work. "
    '"Ah. I\'ve been here since dawn, but the mud is deep. Not much, but a few trinkets."'
)
T2_LINE = '"Thanks, Hal." I head for the northern edge he pointed at and start probing the mud with my boot heel, looking for anything solid worth digging out.'
T2_PROSE = (
    "You head for the northern edge Hal pointed at and start probing the muddy ground with your boot heel. "
    'Hal Garner watches from a distance. "Ah, good find," he says.'
)


class MoralActs(unittest.TestCase):
    def test_reader(self):
        from app.world import _player_moral_act as act

        self.assertEqual(act(T2_LINE, T2_PROSE), "")
        self.assertEqual(act("I still have my mother's reckoner in my pocket, and I keep it there.", "The yard is shut."), "")
        self.assertEqual(act("I give the boy my last copper.", ""), "give")
        self.assertEqual(act("I ask the way.", "You quietly help the old man to his feet."), "help")
        self.assertEqual(act("I ask the way.", "You steal the purse while he looks away."), "steal")
        # Speech and other people's acts are not the player's.
        self.assertEqual(act('"Hal, help me lift this."', "Hal nods."), "")
        self.assertEqual(act("I ask him the way.", "You see him hit the man."), "")
        self.assertEqual(act("I ask the way.", "Hal is grateful for the help."), "")


class KarmaVisibilityIsNotTheBand(unittest.TestCase):
    """KARMA "public" "large" and KARMA "moderate" "private" (runs 5-9): visibility written where the band goes."""

    def test_parse(self):
        from app.turn_dsl import parse_dsl_turn

        turn = parse_dsl_turn('===NAR===\nYou help him up.\n===OPS===\nKARMA "public" "large"\n')
        self.assertEqual((turn["player"].get("karma_band"), turn["player"]["karma_visibility"]), ("large", "public"))
        turn = parse_dsl_turn('===NAR===\nYou help him up.\n===OPS===\nKARMA "moderate" "private" "for helping"\n')
        self.assertEqual((turn["player"].get("karma_band"), turn["player"]["karma_visibility"]), ("moderate", "private"))
        turn = parse_dsl_turn('===NAR===\nYou help him up.\n===OPS===\nKARMA "small" VIS public\n')
        self.assertEqual((turn["player"].get("karma_band"), turn["player"]["karma_visibility"]), ("small", "public"))


class ThroughTheTurn(unittest.TestCase):
    """apply_turn with run 9's T1 and T2: nothing earned, nothing paid."""

    def setUp(self):
        from app import db, rng, world

        db.init_db()
        rng.reset_seed_cache()
        world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})

    def _player(self):
        from app import db

        with db.connect() as conn:
            row = conn.execute("SELECT xp, karma FROM player WHERE id = 1").fetchone()
            return int(row["xp"]), int(row["karma"])

    def _apply(self, prose, line, player):
        from app import world

        turn = {"narration": prose, "player": dict(player), "inventory_changes": []}
        turn["self_check"] = {"passed": True, "issues_found": [], "corrections_made": []}
        turn["turn_summary"] = "test"
        world.apply_turn(turn, line)
        return turn

    def test_t1_xp_for_a_question_is_dropped(self):
        xp, karma = self._player()
        turn = self._apply(T1_PROSE, T1_LINE, {"xp_band": "small"})
        self.assertEqual(self._player(), (xp, karma))
        self.assertIn("xp_dropped", turn.get("_reward_gate") or {})

    def test_t2_karma_for_probing_mud_is_dropped(self):
        xp, karma = self._player()
        self._apply(T2_PROSE, T2_LINE, {"karma_band": "moderate", "karma_reason": "Hal's helpfulness and the treasures found"})
        self.assertEqual(self._player()[1], karma)

    def test_earned_rewards_stand(self):
        xp, karma = self._player()
        self._apply("You help the old woman carry her nets to the cart.", "I help the old woman with her nets.",
                    {"karma_band": "small"})
        self.assertGreater(self._player()[1], karma)
        from app import world

        turn = {"narration": "You pull a brass hinge out of the mud and pocket it.", "player": {"xp_band": "small"},
                "inventory_changes": [{"name": "brass hinge", "quantity_delta": 1}],
                "self_check": {"passed": True, "issues_found": [], "corrections_made": []}, "turn_summary": "test"}
        world.apply_turn(turn, "I dig at the mud, looking for anything worth hauling back.")
        self.assertGreater(self._player()[0], xp)


if __name__ == "__main__":
    unittest.main()
