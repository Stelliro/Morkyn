"""7B run 18, T7: an invented answer to a question put to the player, a reworded line inside her quote, a day rate agreed."""
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-7b-run18-pay-"))
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


LINE = ("\"A share of the salvage is a fine word for 'nothing yet'.\" I rub my arm where it aches. "
        "\"Loading and unloading, I can do. Three gold a day, paid at dusk, and I'll start tomorrow at low tide. Deal?\"")
DRAFT = (
    "You rub your aching arm as you look Wymarc in the eye. \"A share of the salvaged goods sounds better than nothing "
    "yet. Loading and unloading, I can do. Three gold a day, paid at dusk, and I'll start tomorrow at low tide. Deal?\" "
    "Wymarc considers for a moment.\n\n"
    "\"Fair enough, lass,\" he says finally. \"You're a bit hurt there. What happened?\"\n\n"
    "\"I fell into a crate of broken pots. Nothing serious, but it's ached since. I can handle the work, though. "
    "Can I start tomorrow?\"\n\n"
    "\"Of course. We're not expecting any big shipments today.\""
)
ANSWER = ("\"I fell into a crate of broken pots. Nothing serious, but it's ached since. I can handle the work, though. "
          "Can I start tomorrow?\"")


class InventedAnswerToAQuestion(unittest.TestCase):
    """'"You're a bit hurt there. What happened?"' then an untagged first-person answer the player never gave."""

    def test_dropped(self):
        from app.narration_pipeline import drop_invented_player_speech

        _kept, dropped = drop_invented_player_speech(DRAFT.split("\n\n"), LINE)
        self.assertEqual(dropped, [ANSWER])

    def test_scene_ends_at_the_question(self):
        from app import llm

        point = llm._scene_cut_point(DRAFT, LINE)
        self.assertIsNotNone(point)
        self.assertEqual(point["npc_line"], "You're a bit hurt there. What happened?")

    def test_an_npc_answering_the_players_question_stays(self):
        # Run 17 T5: Madoc's "I've got a few" answers the player's own question.
        from app.narration_pipeline import drop_invented_player_speech

        paras = [
            '"Building? I\'m just clearing the mud," Madoc replies.',
            '"Thanks. What about you, Madoc? Any leads on a job around here?" you ask.',
            '"I\'ve got a few, but nothing too urgent. You might find something at the harbour."',
        ]
        line = '"A ploughman? What are you building down here, Madoc?"'
        _kept, dropped = drop_invented_player_speech(paras, line)
        self.assertNotIn(paras[2], dropped)

    def test_an_npc_continuing_without_a_question_stays(self):
        from app.narration_pipeline import drop_invented_player_speech

        paras = ['"Fair enough, lass," he says.', '"I\'ll have the crates ready by dawn."']
        self.assertEqual(drop_invented_player_speech(paras, LINE)[1], [])


class RewordedLineInsideHerQuote(unittest.TestCase):
    """The reworded first line stayed glued before her real second line, and the typed one was said again."""

    def test_restored_in_place(self):
        from app.narration_pipeline import keep_player_words

        text, changes = keep_player_words(DRAFT, LINE)
        self.assertIn("\"A share of the salvage is a fine word for 'nothing yet'. Loading and unloading", text)
        self.assertNotIn("salvaged goods", text)
        self.assertEqual(text.count("fine word for"), 1)
        self.assertEqual([c["action"] for c in changes], ["reworded_line_restored"])


class DayRateAgreed(unittest.TestCase):
    """'Three gold a day ... Deal?' / 'Fair enough, lass ... What happened?' left the rolled 33 gold."""

    def test_agreement_with_an_unrelated_question(self):
        from app.quest_parser import _agrees

        self.assertTrue(_agrees("Fair enough, lass. You're a bit hurt there. What happened?"))
        self.assertFalse(_agrees("Very well, then. What do you have to offer?"))
        self.assertFalse(_agrees("Aye. But how many knives is that?"))

    def test_day_rate_is_the_price(self):
        from app.quest_parser import agreed_job_price

        self.assertEqual(agreed_job_price(DRAFT, LINE), (3, "player_terms_agreed"))

    def test_recorded_per_day(self):
        from app.db import connect, init_db
        from app.quest_parser import settle_agreed_price

        init_db()
        with connect() as conn:
            conn.execute("DELETE FROM quests")
            conn.execute("INSERT INTO npcs (code, name, role, location_id) VALUES ('A', 'Wymarc Lockwood', 'water carrier', 1)")
            npc_id = conn.execute("SELECT id FROM npcs WHERE code = 'A'").fetchone()[0]
            conn.execute(
                "INSERT INTO quests (code, title, description, status, reward_gold, giver_npc_id) VALUES "
                "('Q1', 'Help with loading and unloading', 'Loading. Promised: a share of the salvage', 'active', 33, ?)",
                (npc_id,),
            )
            change = settle_agreed_price(conn, narration=DRAFT.replace("Wymarc", "Wymarc Lockwood"), player_input=LINE,
                                         touched_codes={"Q1"})
            row = conn.execute("SELECT reward_gold, description FROM quests WHERE code = 'Q1'").fetchone()
        self.assertEqual(change["to"], 3)
        self.assertTrue(change["per_day"])
        self.assertEqual(row[0], 3)
        self.assertTrue(row[1].endswith("Promised: 3 gold a day"), row[1])


if __name__ == "__main__":
    unittest.main()
