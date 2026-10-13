"""7B run 18 (Qwen2.5 7B on MLE, agent as player): a venue the player names keeps that name."""
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-7b-run18-"))
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


class NamedVenue(unittest.TestCase):
    """T3: "I push open the door of Pollard's Cookshop" opened "Saltmarrow Diner"."""

    def test_keeps_the_players_name(self):
        from app import world
        from app.db import connect, init_db

        init_db()
        world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
        with connect() as conn:
            here = conn.execute("SELECT current_location_id FROM player").fetchone()[0]
            made = world._mint_venue_from_request(
                conn, here, "\"Ready.\" I push open the door of Pollard's Cookshop and go in.", "You step inside."
            )
        self.assertEqual(made, "Pollard's Cookshop")


class PutGoldDownAfterAnd(unittest.TestCase):
    """T5: "I set a copper-worth of thought aside and put one gold on the counter" moved no gold."""

    def test_pays(self):
        from app.prose_state import player_pays_outright

        self.assertEqual(
            player_pays_outright('"Lovely." I set a copper-worth of thought aside and put one gold on the counter.'), 1
        )
        self.assertIsNone(player_pays_outright("He nods and puts two gold on the bar."))
        self.assertIsNone(player_pays_outright("I sit and count my coins."))


class EatingIsNotCooking(unittest.TestCase):
    """T6: "I eat a few spoonfuls of the stew" rolled cooking, failed, and hurt the player's arm."""

    def test_triggers(self):
        from app.skill_checks import infer_check_from_action as infer

        def skill(line):
            return (infer(line, {}) or {}).get("skill_code")

        self.assertIsNone(skill('I eat a few spoonfuls of the stew before I answer. "Help how?"'))
        self.assertIsNone(skill("I buy some food."))
        self.assertEqual(skill("I cook a stew for the crew."), "cooking")
        self.assertEqual(skill("I roast the gull over the fire."), "cooking")


class SleepIsSilent(unittest.TestCase):
    """T9: a night's sleep became a working day with lines the player never said."""

    def test_sleep_ends_before_her_first_line(self):
        from app import llm

        text = (
            "You sleep in the diner, the fog outside a quiet blanket over the harbour. You wake as the light comes. "
            "Wymarc is at his counter, filling jugs with water from the well, humming to himself.\n\n"
            '"Feeling better, lass?" he asks.\n\n"Thanks for your care," you reply.\n\n'
            'Rusk hands you a rope. "Of course, Captain."'
        )
        turn = {"narration": text, "narration_segments": [{"label": "paragraph", "text": p} for p in text.split("\n\n")]}
        out = llm._end_silent_scene_before_player(turn, "__wait_request__: kind=sleep minutes=600")
        self.assertTrue(out["narration"].endswith('"Feeling better, lass?" he asks.'), out["narration"])


class CaptainOfTheShip(unittest.TestCase):
    """T9: "the captain of the ship, a grizzled man named Rusk" stored his job as "ship"."""

    def test_job(self):
        from app.db import connect, init_db
        from app.world import _roles_stated_in_prose

        init_db()
        with connect() as conn:
            out = _roles_stated_in_prose(
                conn, [{"name": "Rusk", "role": "local"}],
                "As you approach, you see the captain of the ship, a grizzled man named Rusk, who greets you.",
            )
        self.assertEqual(out[0]["role"], "captain")


if __name__ == "__main__":
    unittest.main()
