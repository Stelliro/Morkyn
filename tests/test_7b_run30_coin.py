"""7B run 30, T5: a job's pay asked for is said, and a pouch handed over for the job is its pay."""
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-7b-run30-coin-"))
_ENV = isolated_data_env(str(_TMP))
_SAVED_ENV: dict[str, str | None] = {}

NARRATION = (
    "“Aye, I will help with the traps. What does it pay?” you ask. Dunstan [[A]] looks pleased. "
    "\"We pay a good coin for your work.\"\n\n"
    "Dunstan [[A]] ponders. \"Moles are tricky, but with a few well-placed traps, we should be able to stop them.\" "
    "He hands you a small pouch. \"This should cover it. Let's get to work.\""
)
LINE = '"Aye, I will help with the traps. What does it pay?"'


def setUpModule():
    _SAVED_ENV.update({key: os.environ.get(key) for key in _ENV})
    os.environ.update(_ENV)


def tearDownModule():
    for key, value in _SAVED_ENV.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _fresh_with_job(status: str = "offered"):
    from app import world
    from app.db import connect, init_db

    init_db()
    world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
    with connect() as conn:
        conn.execute("DELETE FROM npcs")
        conn.execute("DELETE FROM quests")
        loc = conn.execute("SELECT current_location_id FROM player").fetchone()[0]
        conn.execute(
            "INSERT INTO npcs (code, location_id, name, role) VALUES ('A', ?, 'Dunstan Wadley', 'mole catcher')", (loc,)
        )
        npc = conn.execute("SELECT id FROM npcs WHERE code = 'A'").fetchone()[0]
        conn.execute(
            "INSERT INTO quests (code, title, description, status, reward_gold, reward_xp, giver_npc_id, notes) "
            "VALUES ('Q1', 'Help with moles', '', ?, 11, 18, ?, '')",
            (status, npc),
        )


class BandedCoinGrantIsCoin(unittest.TestCase):
    """GRANT "11 gold" "moderate" carried no count yet, slipped past the coin take, rolled to 2 and was refused."""

    def test_taken(self):
        from app.world import _take_coin_grants

        result = {"inventory_changes": [{"name": "11 gold", "quantity_band": "moderate"},
                                        {"name": "rope", "quantity_band": "small"}]}
        coins = _take_coin_grants(result)
        self.assertEqual([c["name"] for c in coins], ["11 gold"])
        self.assertEqual([c["name"] for c in result["inventory_changes"]], ["rope"])
        self.assertEqual(_take_coin_grants({"inventory_changes": [{"name": "11 gold", "quantity_band": "-small"}]}), [])


class PouchForTheJobIsItsPay(unittest.TestCase):
    def test_settled_as_the_jobs_pay(self):
        from app import world
        from app.db import connect

        _fresh_with_job()
        result = {"narration": NARRATION, "player": {},
                  "inventory_changes": [{"name": "11 gold", "quantity_band": "moderate"}]}
        with connect() as conn:
            note = world._settle_stated_gold(result, LINE, conn=conn)
        self.assertEqual(note["source"], "prose_received_job_pay")
        self.assertEqual(result["player"]["gold_delta"], 11)
        self.assertEqual(result["inventory_changes"], [])

    def test_a_pouch_without_a_coin_grant_is_not_coin(self):
        from app import world
        from app.db import connect

        _fresh_with_job()
        result = {"narration": NARRATION, "player": {}, "inventory_changes": []}
        with connect() as conn:
            world._settle_stated_gold(result, LINE, conn=conn)
        self.assertFalse(result["player"].get("gold_delta"))

    def test_accepted_this_turn_counts_as_paid_ahead(self):
        from app.db import connect
        from app.quest_parser import advance_paid, job_paid_in_advance, record_advance_pay

        _fresh_with_job(status="active")
        with connect() as conn:
            self.assertIsNone(job_paid_in_advance(conn, narration=NARRATION, coin_in=11))
            job = job_paid_in_advance(conn, narration=NARRATION, coin_in=11, accepted_now={"Q1"})
            self.assertEqual(job["code"], "Q1")
            record_advance_pay(conn, job, coin_in=11, turn=5)
            row = dict(conn.execute("SELECT reward_gold, notes FROM quests WHERE code = 'Q1'").fetchone())
        self.assertEqual(row["reward_gold"], 0)
        self.assertEqual(advance_paid(row), 11)


class PayAskedShipsTheSum(unittest.TestCase):
    def test_fact_and_instruction(self):
        from app.prompts import asked_job_pay
        from app.turn_dsl import build_dsl_user_prompt

        context = {"open_offers": [{"title": "Help with moles", "giver": "Dunstan", "pays_gold": 11, "status": "offered"}]}
        self.assertEqual(asked_job_pay(context, LINE), {"job": "Help with moles", "giver": "Dunstan", "pays": "11 gold"})
        self.assertIsNone(asked_job_pay(context, '"Aye, I will help with the traps."'))
        self.assertIsNone(asked_job_pay({"open_offers": []}, LINE))
        prompt = build_dsl_user_prompt(context, LINE)
        self.assertIn("pay_asked", prompt)
        self.assertIn("11 gold", prompt)

    def test_two_jobs_need_a_name(self):
        from app.prompts import asked_job_pay

        context = {"open_offers": [
            {"title": "Help with moles", "giver": "Dunstan", "pays_gold": 11, "status": "offered"},
            {"title": "Salvage a damaged ship", "giver": "Oswin", "pays_gold": 14, "status": "offered"},
        ]}
        self.assertIsNone(asked_job_pay(context, '"What does it pay?"'))
        self.assertEqual(asked_job_pay(context, '"What does the ship job pay, Oswin?"')["pays"], "14 gold")


if __name__ == "__main__":
    unittest.main()
