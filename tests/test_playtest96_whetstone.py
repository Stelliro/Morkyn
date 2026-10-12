"""Playtest #96-#99: the README example turn on the 8B (copy of save 83a1ec4c, turn 9).

"I set the last polished blade on the rack and ask Finnian if he'd sell me a
whetstone. I'll pay 2 gold for it." The draft showed the coins paid and the
stone handed over; the engine then:

- #97 cut "You pull out two gold coins ... and hand them over" as an act the
  player never asked for, although the line offered the 2 gold;
- #96 refused the whetstone (the final prose hands over "it", and buying was
  not read as asking for anything), then voided the 2 gold;
- #98 completed two quests off the one sentence and paid both;
- #99 rolled QTY moderate into two whetstones.

These pin the engine side of each fix without a model.
"""
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-playtest96-"))
_ENV = isolated_data_env(str(_TMP))
os.environ.update(_ENV)

from app import llm, quest_parser, world  # noqa: E402

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


LINE = "I set the last polished blade on the rack and ask Finnian if he'd sell me a whetstone. I'll pay 2 gold for it."
FINAL = (
    "You set the last polished blade on the rack and ask Finnian if he'd sell you a whetstone. He looks up "
    "from his bench. “It's a little pricey, though. Two gold for it.”\n\n"
    "You pull out two gold coins from your pouch and hand them over. Finnian takes the coins with a grunt, then "
    "pulls out a rough-hewn stone the size of your palm. “This'll keep your blade sharp,” he says, handing it to you."
)


class BuyingIsAsking(unittest.TestCase):
    def test_a_purchase_ask_is_take_intent(self):
        self.assertTrue(llm.player_take_intent(LINE))
        self.assertTrue(llm.player_take_intent("could you sell me some rope?"))
        self.assertTrue(llm.player_take_intent("I pay the ferryman three coins for passage"))
        self.assertFalse(llm.player_take_intent("I ask Finnian how long he has worked here"))

    def test_the_bought_item_is_granted(self):
        from app.db import connect, init_db

        init_db()
        rejected: list[dict] = []
        with connect() as conn:
            kept = world._filter_inventory_changes(
                conn,
                [{"name": "whetstone", "quantity_delta": 1}],
                narration=FINAL,
                player_input=LINE,
                draft_narration=FINAL + " You nod, tucking the whetstone into your satchel.",
                rejected=rejected,
            )
        self.assertEqual([c["name"] for c in kept], ["whetstone"], rejected)


class OfferedCoinIsThePlayersAct(unittest.TestCase):
    def test_the_payment_sentence_stays(self):
        text, dropped = llm.drop_invented_player_acts_text(FINAL, LINE)
        self.assertIn("You pull out two gold coins", text)
        self.assertFalse(any("gold coins" in d for d in dropped), dropped)

    def test_coin_with_no_payment_in_the_line_still_goes(self):
        text, dropped = llm.drop_invented_player_acts_text(
            "You pull out two gold coins from your pouch and hand them over. The guard grunts and waves you on.",
            "I ask the guard what happened here.",
        )
        self.assertNotIn("gold coins", text)
        self.assertTrue(dropped)


class OneActOneQuest(unittest.TestCase):
    EXISTING = [
        {"id": 2, "code": "Q2", "title": "Learn metalworking", "status": "active",
         "current_step_text": "Learn metalworking Learn more about metalworking, starting with polishing swords"},
        {"id": 1, "code": "Q1", "title": "Polish swords", "status": "active",
         "current_step_text": "Polish swords Start by helping Finnian polish these swords"},
    ]
    EVIDENCE = "You set the last polished blade on the rack and ask Finnian"

    def _validate(self, updates):
        return quest_parser.validate_quest_changes(
            {"new": [], "updates": updates},
            narration=FINAL,
            player_input=LINE,
            existing=self.EXISTING,
        )

    def test_one_sentence_advances_one_quest(self):
        accepted, rejected = self._validate(
            [
                {"quest": "Q1", "action": "step_done", "evidence": self.EVIDENCE},
                {"quest": "Q2", "action": "step_done", "evidence": self.EVIDENCE},
            ]
        )
        self.assertEqual([u["code"] for u in accepted["updates"]], ["Q1"])
        self.assertTrue(any("same_act_as:Q1" in r["reasons"] for r in rejected), rejected)

    def test_the_better_fit_wins_whatever_the_order(self):
        accepted, _ = self._validate(
            [
                {"quest": "Q2", "action": "step_done", "evidence": self.EVIDENCE},
                {"quest": "Q1", "action": "step_done", "evidence": self.EVIDENCE},
            ]
        )
        self.assertEqual([u["code"] for u in accepted["updates"]], ["Q1"])

    def test_two_acts_advance_two_quests(self):
        accepted, _ = self._validate(
            [
                {"quest": "Q1", "action": "step_done", "evidence": self.EVIDENCE},
                {"quest": "Q2", "action": "step_done", "evidence": "Finnian takes the coins with a grunt"},
            ]
        )
        self.assertEqual(sorted(u["code"] for u in accepted["updates"]), ["Q1", "Q2"])


class OneThingNamedIsOne(unittest.TestCase):
    def test_named_once(self):
        self.assertTrue(world._item_named_as_one("whetstone", LINE + "\n" + FINAL))
        self.assertTrue(world._item_named_as_one("Rye bread", "I buy the rye bread"))

    def test_a_count_or_plural_leaves_the_band(self):
        self.assertFalse(world._item_named_as_one("arrow", "he hands you a quiver and two arrows"))
        self.assertFalse(world._item_named_as_one("berry", "a handful of berry clusters, a berry"))
        self.assertFalse(world._item_named_as_one("ration", "three ration packs"))
        self.assertFalse(world._item_named_as_one("ration", "the ration and some ration bars"))

    def test_the_band_rolls_one(self):
        from app.db import connect, init_db

        init_db()
        result = {"narration": FINAL, "inventory_changes": [{"name": "whetstone", "quantity_band": "moderate"}]}
        with connect() as conn:
            world.resolve_turn_bands(conn, result, turn=9, player_input=LINE)
        self.assertEqual(result["inventory_changes"][0]["quantity_delta"], 1)

    def test_a_stack_still_rolls(self):
        from app.db import connect, init_db

        init_db()
        result = {"narration": "She tips a pile of arrows into your hands.", "inventory_changes": [{"name": "arrow", "quantity_band": "large"}]}
        with connect() as conn:
            world.resolve_turn_bands(conn, result, turn=9, player_input="I take the arrows")
        self.assertGreater(result["inventory_changes"][0]["quantity_delta"], 1)


if __name__ == "__main__":
    unittest.main()
