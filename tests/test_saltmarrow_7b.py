"""Fixes from the Saltmarrow run on Qwen2.5 7B (MLE), the player played by an agent."""
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-salt7b-"))
_ENV = isolated_data_env(str(_TMP))
os.environ.update(_ENV)

from app import world  # noqa: E402
from app.llm import player_take_intent  # noqa: E402

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


class NamedIsNotReached(unittest.TestCase):
    """T5: a question to the clerk moved the player to the channels the prose only looked at."""

    def _move(self, dest, line, narration):
        return world._unasked_unshown_move({}, {"move_to_location": dest}, [], line, intent="conversation", narration=narration)

    def test_place_in_view_is_not_a_move(self):
        prose = (
            "You thank Osric [[A]] for the information and head towards the wharf. "
            "You turn back to the sea, the salt-choked channels stretching out before you."
        )
        self.assertEqual(self._move("Salt-choked Channels", "How many coin, exactly?", prose), "Salt-choked Channels")

    def test_reaching_it_or_asking_for_it_stands(self):
        self.assertEqual(self._move("The Chandlery", "Hello?", "You step into the chandlery, where rope hangs from every beam."), "")
        self.assertEqual(self._move("The Customs Tower", "I hold on.", "Jocosa poles the door through the rows to the tower."), "")
        self.assertEqual(self._move("The Old Fish Market", "Row me out to the old fish market.", "The roofs slide past."), "")


class SalvageGuildIsNotSalvaging(unittest.TestCase):
    """T3: 'the salvage guild's tally board' read as a take, so a job's anchor was granted."""

    def test_noun_vs_verb(self):
        self.assertFalse(player_take_intent("I head to the salvage guild's tally board to see what work is posted."))
        self.assertTrue(player_take_intent("I salvage the copper from the wreck."))
        self.assertTrue(player_take_intent("salvaging what I can"))


class CoinsAreGold(unittest.TestCase):
    """T5: GRANT "copper" TYPE coin put 'copper x1' in the pack and nothing in the purse."""

    def test_coin_grant_goes_to_the_purse(self):
        from app.db import connect, init_db

        init_db()
        with connect() as conn:
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.execute("DELETE FROM player")
            conn.execute(
                "INSERT INTO player (id, name, health, max_health, level, xp, gold, karma, current_location_id) "
                "VALUES (1, 'Isk', 20, 20, 1, 0, 12, 0, 0)"
            )
            changes = [
                {"name": "copper", "quantity_delta": 1, "item_type": "coin"},
                {"name": "rope", "quantity_delta": 1},
                {"name": "copper ingot", "quantity_delta": 1},
            ]
            kept = world._coins_to_gold(conn, changes, "Grimes hands you three coins.")
            self.assertEqual([c["name"] for c in kept], ["rope", "copper ingot"])
            self.assertEqual(conn.execute("SELECT gold FROM player").fetchone()[0], 15)


class LossesMustBeShown(unittest.TestCase):
    """T7: TAKE of boots, tunic, breeches and the reckoner on a walk emptied the pack."""

    WALK = (
        "You fold the notice into your tunic, check the brass tide-reckoner, and head down the slipway to look for "
        "the lost goods. You scan the horizon, the tide-reckoner in hand."
    )

    def test_unshown_losses_refused(self):
        for item in ("soft-soled boots", "patched tunic", "mother's brass tide-reckoner"):
            self.assertFalse(world._loss_shown(item, self.WALK), item)

    def test_shown_losses_stand(self):
        self.assertTrue(world._loss_shown("bread", "You eat the bread in three bites."))
        self.assertTrue(world._loss_shown("rope", "I give Tam the rope."))
        self.assertTrue(world._loss_shown("rope", "The rope snaps and is swept away."))

    def test_gate_keeps_the_pack(self):
        from app.db import connect, init_db

        init_db()
        with connect() as conn:
            conn.execute("DELETE FROM inventory")
            conn.execute("INSERT INTO inventory (code, name, quantity) VALUES ('I71', 'patched tunic', 1)")
            conn.execute("INSERT INTO inventory (code, name, quantity) VALUES ('I72', 'bread', 1)")
            kept = world._filter_inventory_changes(
                conn,
                [{"name": "patched tunic", "quantity_delta": -1}, {"name": "bread", "quantity_delta": -1}],
                narration=self.WALK + " You eat the bread as you go.",
                player_input="I head onto the flats.",
            )
            self.assertEqual([c["name"] for c in kept], ["bread"])


class RewardQuestionIsNotAppraising(unittest.TestCase):
    """T6: "what's it worth when I bring it in?" rolled a failed appraise and a blunder."""

    def test_job_pay(self):
        from app.skill_checks import infer_check_from_action

        line = 'I take down the notice. "Who posted it, and what\'s it worth when I bring it in?"'
        self.assertIsNone(infer_check_from_action(line, {}))
        self.assertEqual(infer_check_from_action("what is the ring worth?", {})["skill_code"], "appraise")


class SettingOutIsNotDone(unittest.TestCase):
    """T7: 'head down ... to look for the lost cargo' completed and paid the job."""

    def test_intent_only(self):
        from app.quest_parser import _intent_only

        self.assertTrue(_intent_only("you head down the slipway onto the northern mudflats to look for the lost cargo."))
        self.assertFalse(_intent_only("You find the crate half sunk and haul it out."))
        self.assertFalse(_intent_only("You ring the bell."))


class BracketedNames(unittest.TestCase):
    """T0: '[[Bertram Yates]]' and 'a [[R1]] human' shipped as markup."""

    def test_unwrapped(self):
        from app import llm

        out = llm._repair_prose_entity_labels("A man, [[Bertram Yates]], a [[R1]] human sexton, emerges. Madoc [[A]] nods.", {"A": "Madoc"})
        self.assertIn("A man, Bertram Yates, a human sexton", out)
        self.assertIn("Madoc [[A]]", out)


if __name__ == "__main__":
    unittest.main()
