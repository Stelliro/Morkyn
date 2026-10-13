"""7B run 11 (Qwen2.5 7B on MLE, agent as player): a counted coin, others' lies, a board's job."""
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-7b-run11-"))
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


T2_LINE = (
    'I stay where I am by the stable. "The notice board by the inn, then. Which inn, Iseult - '
    'there are three in this town and they all lie."'
)


class ACountedCoinIsItsCount(unittest.TestCase):
    """T2: "Iseult nods and hands you a coin" rolled a small band: +7 gold."""

    def test_counted_coins(self):
        from app.prose_state import counted_coins

        self.assertEqual(counted_coins("hands you a coin"), 1)
        self.assertEqual(counted_coins("hands you two coins"), 2)
        self.assertEqual(counted_coins("presses a pair of coins into your hand"), 2)
        self.assertEqual(counted_coins("hands you a single gold coin"), 1)
        for vague in ("places a handful of polished coins in your palm", "hands you a few coins",
                      "hands over a moderate bag of coin", "hands you three silver coins", "gives you the coins"):
            self.assertIsNone(counted_coins(vague), vague)

    def _settle(self, narration, line="I wait."):
        from app import world
        from app.db import connect, init_db

        init_db()
        result = {"narration": narration, "player": {}}
        with connect() as conn:
            note = world._settle_stated_gold(result, line, conn=conn)
        return result, note

    def test_one_coin_moves_one_gold(self):
        result, note = self._settle('Iseult nods and hands you a coin. "Good luck."')
        self.assertEqual(result["player"].get("gold_delta"), 1, note)
        self.assertNotIn("gold_band", result["player"])

    def test_a_vague_amount_still_rolls(self):
        result, _ = self._settle("She places a handful of polished coins in your palm.")
        self.assertIn("gold_band", result["player"])


class OthersLyingIsNotDeception(unittest.TestCase):
    """T2: "...they all lie." rolled deception, a critical failure ("Botched Deception")."""

    def test_others(self):
        from app.skill_checks import infer_check_from_action as infer

        self.assertNotEqual((infer(T2_LINE) or {}).get("skill_code"), "deception")
        self.assertNotEqual((infer('"The merchants cheat everyone here," I say.') or {}).get("skill_code"), "deception")

    def test_the_players_own(self):
        from app.skill_checks import infer_check_from_action as infer

        self.assertEqual(infer('"I am a guild inspector," I lie.')["skill_code"], "deception")
        self.assertEqual(infer("I lie to the guard about my name.")["skill_code"], "deception")
        self.assertEqual(infer("I threaten him with my hook.")["skill_code"], "intimidation")


class ABoardsJobIsTheBoards(unittest.TestCase):
    """T2: a job read off the inn's board was filed under Iseult, who only said where the board was."""

    # The run's own paragraphs.
    NARRATION = (
        'Iseult Pennick [[A]] nods, her eyes thoughtful. "The Leaning Spindle, The Pear at Saltmarrow, or The '
        "Crooked Plough. I've heard the Spindle's board is the least likely to be full of lies, but that's just the "
        'talk of the town."\n\n'
        "You make your way to the board that hangs above the fireplace. It is covered with postings, each one more "
        "enticing than the last. You scan the notices, looking for any that might interest you.\n\n"
        "You thank her and continue your search, eventually deciding on a task that seems feasible. You read the "
        'details aloud: "Lifting supplies to the upper levels of the market hall. They need a strong back."\n\n'
        'Iseult nods and hands you a coin. "Good luck. They\'ll be waiting for you at the market hall."'
    )
    NPCS = [{"id": 1, "code": "A", "name": "Iseult Pennick"}]

    def _offer(self, evidence):
        return {"new": [{
            "title": "Lifting supplies to the upper levels", "summary": "x", "giver": "A",
            "steps": [{"title": "Head to the market hall", "location": "L1"}], "reward": {"gold": 0},
            "difficulty": "easy", "evidence": evidence,
            # The parser's offer_line in the run, which grounded the offer.
            "offer_line": 'Iseult nods and hands you a coin. "Good luck. They\'ll be waiting for you at the market hall."',
        }], "updates": []}

    def test_board(self):
        from app import quest_parser as qp

        evidence = 'You read the details aloud: "Lifting supplies to the upper levels of the market hall. They need a strong back."'
        accepted, rejected = qp.validate_quest_changes(
            self._offer(evidence), narration=self.NARRATION, player_input=T2_LINE, npcs=self.NPCS
        )
        self.assertEqual(rejected, [])
        self.assertEqual(accepted["new"][0]["giver"], "the notice board")
        self.assertFalse(accepted["new"][0].get("giver_npc_id"))

    def test_a_poster_named_on_it_keeps_the_job(self):
        from app import quest_parser as qp

        narration = self.NARRATION.replace("They need a strong back.", "They need a strong back. Ask Iseult.")
        evidence = 'You read the details aloud: "Lifting supplies to the upper levels of the market hall. They need a strong back. Ask Iseult."'
        accepted, _ = qp.validate_quest_changes(
            self._offer(evidence), narration=narration, player_input=T2_LINE, npcs=self.NPCS
        )
        self.assertEqual(accepted["new"][0]["giver"], "A")


if __name__ == "__main__":
    unittest.main()
