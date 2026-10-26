"""7B run 5 money and pack fixes (#125, #126): payments, wages, takes, gives and sales the prose shows."""
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-7b-run5-money-"))
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


def _fresh(conn, inventory=(), narrations=()):
    conn.execute("DELETE FROM inventory")
    conn.execute("DELETE FROM journal")
    for number, (name, qty) in enumerate(inventory, start=1):
        conn.execute("INSERT INTO inventory (code, name, quantity) VALUES (?, ?, ?)", (f"I{number}", name, qty))
    for text in narrations:
        conn.execute("INSERT INTO journal (turn, kind, content) VALUES (1, 'narration', ?)", (text,))


def _turn(narration, player=None, changes=None):
    return {"narration": narration, "player": dict(player or {}), "inventory_changes": list(changes or [])}


class ProseReaders(unittest.TestCase):
    def test_money_put_down_is_paid(self):
        from app.prose_state import stated_coin_amounts as read

        self.assertEqual(read("You put two gold coins on the bar, just like last time.")["paid"], [2])
        self.assertEqual(read("You set out with ten gold in your purse.")["paid"], [])
        self.assertEqual(read("You put three coins into your purse.")["paid"], [])

    def test_payment_with_no_sum(self):
        from app.prose_state import shows_unpriced_payment as shows

        self.assertTrue(shows("You pay her the agreed price, and she wraps it carefully in a cloth."))
        self.assertTrue(shows("you comment, counting out the gold pieces he asks for."))
        self.assertTrue(shows("You pay for the lantern and leave."))
        self.assertFalse(shows("You pay attention to the road."))
        self.assertFalse(shows("You pay him a visit."))

    def test_coin_handed_to_the_player(self):
        from app.prose_state import coin_handed_to_player as handed

        self.assertEqual(handed("Abel Hollis [[D]] nods and hands over a moderate bag of coin for your efforts.")["band"], "moderate")
        self.assertIsNotNone(handed("He hesitates before reaching into his pouch and handing you the coins."))
        self.assertIsNone(handed("You hand over three coins."))
        self.assertIsNone(handed("She hands you the lamp."))
        self.assertIsNone(handed("He hands the coins to the clerk."))
        self.assertIsNone(handed("Roger hands you a heavy purse of silver."))

    def test_line_pays_outright(self):
        from app.prose_state import player_pays_outright as outright

        self.assertEqual(outright("I put two gold on the bar for the room, like last time, and ask Verity to wake me."), 2)
        self.assertEqual(outright("I pay him three coins."), 3)
        self.assertIsNone(outright("I'll give you 3 gold for that."))
        self.assertIsNone(outright("I put 4 gold down, is that enough?"))
        self.assertIsNone(outright("I don't put 4 gold down."))


class SettleGold(unittest.TestCase):
    def setUp(self):
        from app.db import init_db

        init_db()

    def _settle(self, result, line, *, inventory=(), narrations=(), quest_pays=False):
        from app import world
        from app.db import connect

        with connect() as conn:
            _fresh(conn, inventory, narrations)
            return world._settle_stated_gold(result, line, conn=conn, quest_pays=quest_pays)

    def test_t94_money_on_the_bar(self):
        result = _turn("You put two gold coins on the bar, just like last time, and ask Verity [[H]] to wake you.")
        note = self._settle(result, "I put two gold on the bar for the room, like last time, and ask Verity to wake me.")
        self.assertEqual(result["player"]["gold_delta"], -2, note)

    def test_t94_line_alone_pays_when_prose_does_not_refuse(self):
        result = _turn("Verity nods and slides the key across. \"Room's yours.\"")
        note = self._settle(result, "I put two gold on the bar for the room.")
        self.assertEqual((result["player"]["gold_delta"], note["source"]), (-2, "player_paid"))

    def test_t94_line_refused_pays_nothing(self):
        result = _turn("Verity pushes the coins back. \"Keep your coin, love.\"")
        self._settle(result, "I put two gold on the bar for the room.")
        self.assertNotIn("gold_delta", result["player"])

    def test_t48_price_named_in_the_scene(self):
        result = _turn(
            '"I don\'t think I paid you for the iron lamp," you comment, counting out the gold pieces he asks for. '
            '"Four gold pieces should cover it," he says.'
        )
        note = self._settle(result, "What do I owe? I count out what she asks.")
        self.assertEqual((result["player"]["gold_delta"], note["source"]), (-4, "price_named_in_scene"))

    def test_t47_agreed_price_from_an_earlier_scene(self):
        result = _turn("You pay her the agreed price, and she wraps the lantern in a cloth.",
                       changes=[{"name": "iron lantern", "quantity_delta": 1}])
        note = self._settle(result, "I buy the lantern.",
                            narrations=['The chandler taps the lantern. "That\'ll be 3 gold, flat-runner."'])
        self.assertEqual((result["player"]["gold_delta"], note["source"]), (-3, "price_agreed_earlier"))

    def test_t47_no_quote_anywhere_moves_nothing(self):
        # Was a rolled small spend: since fantasy100 (F188 cont. 4) the die never sizes money.
        result = _turn("You pay her the agreed price, and she wraps it carefully in a cloth.",
                       changes=[{"name": "iron lantern", "quantity_delta": 1}])
        note = self._settle(result, "I buy a lantern.")
        self.assertEqual(note["source"], "payment_unpriced_held")
        self.assertNotIn("gold_band", result["player"])
        self.assertFalse(result["player"].get("gold_delta"))

    def test_t72_wages_with_only_a_size_word_move_nothing(self):
        # Was the size word rolled: since fantasy100 (F188 cont. 4) no die sizes money.
        result = _turn("Abel Hollis [[D]] nods and hands over a moderate bag of coin for your efforts.",
                       changes=[{"name": "Five gold coins", "quantity_delta": 4}])
        note = self._settle(result, "Then I tell Abel it's finished and ask for the coin.")
        self.assertEqual(note["source"], "received_coin_unsummed_held")
        self.assertNotIn("gold_band", result["player"])
        self.assertEqual(result["inventory_changes"], [])  # coin is never a pack item

    def test_t55_sale_coin_takes_the_named_sum(self):
        result = _turn(
            "You push the brass fittings across the table and hold out your hand for the ten gold. "
            "He hesitates a beat before reaching into his pouch and handing you the coins.",
            changes=[{"name": "sixteen gold", "quantity_delta": 2}],
        )
        note = self._settle(result, '"Ten gold for the lot. Done." I push the fittings across the desk.')
        self.assertEqual((result["player"]["gold_delta"], note["source"]), (10, "prose_received_named"))

    def test_received_with_a_number(self):
        result = _turn("Warin hands you 6 gold and nods.")
        self._settle(result, "I ask for my pay.")
        self.assertEqual(result["player"]["gold_delta"], 6)

    def test_quest_payout_turn_mints_nothing_more(self):
        result = _turn("Warin hands you 6 gold and nods.")
        self._settle(result, "I ask for my pay.", quest_pays=True)
        self.assertNotIn("gold_delta", result["player"])

    def test_coin_grant_without_coin_shown_is_dropped(self):
        result = _turn('"Small job, but it pays well," Roger says.', changes=[{"name": "Five gold coins", "quantity_delta": 2}])
        self._settle(result, "How much does it pay?")
        self.assertEqual(result["inventory_changes"], [])
        self.assertNotIn("gold_delta", result["player"])
        self.assertNotIn("gold_band", result["player"])

    def test_model_gold_op_still_wins(self):
        result = _turn("Abel hands you 4 gold for your efforts.", player={"gold_delta": 4})
        note = self._settle(result, "I ask for the coin.")
        self.assertEqual((result["player"]["gold_delta"], note["source"]), (4, "stated_gain"))


class TakesAndGives(unittest.TestCase):
    def setUp(self):
        from app.db import init_db

        init_db()

    def _takes(self, line, prose, *, inventory=(), narrations=()):
        from app import world
        from app.db import connect

        with connect() as conn:
            _fresh(conn, inventory, narrations)
            return world._grant_shown_takes(conn, [], prose, line)

    def _gives(self, line, prose, inventory):
        from app import world
        from app.db import connect

        with connect() as conn:
            _fresh(conn, inventory)
            return world._remove_shown_gives(conn, [], prose, line)

    def test_t12_find_yourself_with(self):
        added = self._takes(
            '"Found it first," I tell Abel. I take the leather-bound book and the scrolls, wrap them in my shirt tail, and keep them.',
            "You find yourself with a leather-bound book and some scrolls, their pages damp from the sea air. "
            "You wrap them in your shirt tail, tucking them carefully away.",
        )
        self.assertEqual(sorted(a["name"] for a in added), ["leather-bound book", "scrolls"])

    def test_t58_keep_named_by_the_last_scene(self):
        added = self._takes(
            "I keep the fitting I just pulled out of the mud. Then I hold the lantern up.",
            "You keep the shiny bronze-finished piece you just pulled out of the mud. The lantern casts a glow.",
            narrations=["You notice an old brass fitting partially buried in the mud. You pocket it."],
        )
        self.assertEqual([a["name"] for a in added], ["old brass fitting"])

    def test_keep_walking_is_not_a_take(self):
        added = self._takes("I keep the lantern lit and walk on.", "You keep walking, the lantern swinging.",
                            inventory=[("iron lantern", 1)])
        self.assertEqual(added, [])

    def test_t75_give_and_drop(self):
        out = self._gives(
            'I give Abel the old bowl from my pack. "Keep it, I\'ve no use for it." Then I drop the junk cot by the scrap heap.',
            "You give Abel the old bowl [[I7]] from your pack. Then you drop the junk cot [[I6]] by the scrap heap.",
            [("old bowl", 1), ("junk cot", 1), ("iron lantern", 1)],
        )
        self.assertEqual(sorted((c["name"], c["quantity_delta"]) for c in out), [("junk cot", -1), ("old bowl", -1)])

    def test_t55_sale_takes_the_whole_lot(self):
        out = self._gives(
            '"Ten gold for the lot. Done." I push the fittings across the desk and hold out my hand for the coin.',
            "You push the brass fittings [[I8]] across the table and hold out your hand for the ten gold.",
            [("brass fittings", 3)],
        )
        self.assertEqual([(c["name"], c["quantity_delta"]) for c in out], [("brass fittings", -3)])

    def test_t41_putting_it_on_the_scale_to_ask_is_not_a_sale(self):
        out = self._gives(
            "I go into the salvage yard, put the fittings on Roger's scale and ask him what he'll pay for them.",
            "You set the brassy fitting on the scale, and he looks up.",
            [("brass fittings", 2)],
        )
        self.assertEqual(out, [])

    def test_handed_back_is_kept(self):
        out = self._gives(
            "I give Abel the old bowl.",
            "You give Abel the old bowl. He hands it back with a shake of the head.",
            [("old bowl", 1)],
        )
        self.assertEqual(out, [])


if __name__ == "__main__":
    unittest.main()
