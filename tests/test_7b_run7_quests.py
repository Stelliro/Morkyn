"""Jobs in the seventh Saltmarrow run on Qwen2.5 7B: the player takes a job, or turns it down, in their own words."""
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-7b-run7-quests-"))
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


DECK_JOB = {"id": 1, "code": "Q1", "title": "Cleaning the decks", "status": "offered", "current_step": 1, "total_steps": 1}
T3_LINE = "\"Half the usual of what? Give me a number, Oriel, or I'm off to the flats on my own.\""
T3_NARRATION = (
    "The flats beckon, but there's still a chance to earn a bit here. \"Half the usual of what? Give me a number, "
    "Oriel, or I'm off to the flats on my own,\" you say, stepping towards the deck.\n\n"
    "Oriel's eyes light up. \"Good choice. Let's see what the deck has in store for us.\""
)
T4_LINE = "I stop where I am and fold my arms. \"I haven't said yes yet. A number, Oriel. How many coins for clearing that deck?\""
T5_LINE = ("\"Coppers won't touch my debt.\" I shake my head. \"No deal, Oriel. I'll take my chances on the flats.\" "
           "I leave the yard and walk out onto the mudflats toward the drowned lower district.")


def _accept(player_input, narration=T3_NARRATION, quest=DECK_JOB):
    from app import quest_parser

    return quest_parser.validate_quest_changes(
        {"updates": [{"quest": "Q1", "action": "accept", "evidence": "Good choice. Let's see what the deck has in store for us."}]},
        narration=narration, player_input=player_input, existing=[quest],
    )


class TheProseDoesNotTakeTheJob(unittest.TestCase):
    """T3: the parser cited Oriel's 'Good choice' as the accept while Isk only asked for a number."""

    def test_asking_for_a_number_is_not_a_yes(self):
        accepted, rejected = _accept(T3_LINE)
        self.assertEqual(accepted["updates"], [])
        self.assertIn("player_did_not_accept", rejected[0]["reasons"])

    def test_the_players_yes_takes_it(self):
        for line in ("\"Fine, I'll take the job.\"", "\"Deal, Oriel.\"", "\"All right. I'll start on the deck now.\"",
                     "I grab a broom and start on the deck.", "I clean the deck from bow to stern."):
            with self.subTest(line=line):
                accepted, rejected = _accept(line)
                self.assertEqual([u["action"] for u in accepted["updates"]], ["accept"], rejected)

    def test_holding_off_is_not_a_yes(self):
        accepted, _ = _accept(T4_LINE)
        self.assertEqual(accepted["updates"], [])

    def test_the_players_own_price_agreed_is_a_yes(self):
        # Run 6, T6: Isk named the price and Oldfield agreed.
        from app import quest_parser

        line = "\"Three hundred is what's in the sacks.\" I fold my arms. \"Two gold for the whole pile, sorted by noon. Yes or no?\""
        narration = ("\"Two gold for the whole pile, sorted by noon. Yes or no?\" you say.\n\n"
                     "Oldfield nods slowly. \"I suppose we can agree to that. If the job is done by noon, the gold is yours.\"")
        quest = {"id": 1, "code": "Q1", "title": "Sort salvaged goods", "status": "offered"}
        self.assertTrue(quest_parser.player_takes_job(quest, line, [quest], narration))

    def test_walking_off_is_not_starting(self):
        from app import quest_parser

        self.assertFalse(quest_parser.player_takes_job(DECK_JOB, "I start back toward the gate.", [DECK_JOB]))


class AnOfferTakenTheSameTurn(unittest.TestCase):
    """The baseline test: a new job is an offer unless the player's own line takes it."""

    def test_new_job_status(self):
        from app import quest_parser

        changes = {"new": [{"title": "Haul the silk bales", "giver": "", "evidence": "Haul the silk bales to the barge and I'll pay you",
                            "offer_line": "Haul the silk bales to the barge and I'll pay you", "status": "active",
                            "steps": [{"title": "Haul the bales"}]}]}
        narration = "The merchant says, \"Haul the silk bales to the barge and I'll pay you.\""
        out = quest_parser.validate_quest_changes(changes, narration=narration, player_input="Do you need a hand?")[0]
        self.assertEqual(out["new"][0]["status"], "offered")
        out = quest_parser.validate_quest_changes(changes, narration=narration, player_input="I'll take the job.")[0]
        self.assertEqual(out["new"][0]["status"], "active")


class ThePlayersNoIsANo(unittest.TestCase):
    """T4-T5: 'I haven't said yes yet' and 'No deal, Oriel' left the job active."""

    def setUp(self):
        from app.db import connect, init_db
        from app.quests import create_quest

        init_db()
        with connect() as conn:
            for table in ("quest_steps", "quests", "npcs", "journal"):
                conn.execute(f"DELETE FROM {table}")
            conn.execute("INSERT OR IGNORE INTO locations (code, name) VALUES ('L71', 'Run7 Yard')")
            yard = conn.execute("SELECT id FROM locations WHERE code = 'L71'").fetchone()[0]
            conn.execute("INSERT OR IGNORE INTO locations (code, name) VALUES ('L72', 'Run7 Flats')")
            if not conn.execute("SELECT 1 FROM player WHERE id = 1").fetchone():
                conn.execute("INSERT INTO player (id, name) VALUES (1, 'Isk')")
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (yard,))
            conn.execute("INSERT INTO npcs (code, name, role, location_id) VALUES ('A', 'Oriel Rendle', 'overseer', ?)", (yard,))
            oriel = conn.execute("SELECT id FROM npcs WHERE code = 'A'").fetchone()[0]
            self.qid = create_quest(conn, title="Cleaning the decks", steps=[{"title": "Clean the decks"}],
                                    giver_npc_id=oriel, created_turn=3, status="offered")
            conn.commit()

    def _status(self):
        from app.db import connect

        with connect() as conn:
            return conn.execute("SELECT status FROM quests WHERE id = ?", (self.qid,)).fetchone()[0]

    def _take_wrongly_at(self, turn):
        from app.db import connect
        from app.quests import accept_offered

        with connect() as conn:
            accept_offered(conn, self.qid, turn=turn)
            conn.commit()

    def _answer(self, line, turn):
        from app.db import connect
        from app.quest_parser import settle_player_answer

        with connect() as conn:
            rows = settle_player_answer(conn, line, turn)
            conn.commit()
        return rows

    def test_not_yet_puts_a_wrongful_accept_back(self):
        self._take_wrongly_at(4)
        self.assertEqual(self._answer(T4_LINE, 5)[0]["action"], "unaccept")
        self.assertEqual(self._status(), "offered")

    def test_no_deal_turns_it_down(self):
        self._take_wrongly_at(4)
        self.assertEqual(self._answer(T5_LINE, 5)[0]["action"], "decline")
        self.assertEqual(self._status(), "declined")

    def test_no_deal_turns_down_an_offer(self):
        self.assertEqual(self._answer(T5_LINE, 5)[0]["action"], "decline")
        self.assertEqual(self._status(), "declined")

    def test_a_job_long_taken_is_not_undone(self):
        self._take_wrongly_at(1)
        self.assertEqual(self._answer(T4_LINE, 9), [])
        self.assertEqual(self._status(), "active")

    def test_a_no_to_someone_else_leaves_the_job(self):
        from app.db import connect

        with connect() as conn:
            flats = conn.execute("SELECT id FROM locations WHERE code = 'L72'").fetchone()[0]
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (flats,))
            conn.commit()
        self.assertEqual(self._answer("\"No deal, not at that price.\" I put the knife back on the stall.", 5), [])
        self.assertEqual(self._status(), "offered")

    def test_a_plain_line_changes_nothing(self):
        self._take_wrongly_at(4)
        self.assertEqual(self._answer("I sweep the deck and stack the planks.", 5), [])
        self.assertEqual(self._status(), "active")


if __name__ == "__main__":
    unittest.main()
