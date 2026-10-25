"""trade-atomic (cheat100, Hermes 3 8B played by Sonnet like AI Dungeon, 2026-10-25): a trade applied one-sided.

The first slice of m0 (CLAUDE.md "Transactions are settled before the draft"): a sale or barter in the
player's line is applied as one unit or held, at the one place both halves meet
(world._settle_trade, after the gold gates and the item readers, before anything is written).

T23 "I sell the sword to Bartholomew for 500 gold, he hands me the coins, ...": the prose never reached
the counter with coin (gain_without_coin_dropped 500), the give reader still let the sword go (1 -> 0),
gold 12 -> 12. T31 the shortsword for 40 gold ("he carefully counts out forty gold pieces, then pockets
them"): gone, gold 12. T34 the mother's brass tide-reckoner for 300 gold: gone, a -397 die voided, gold
12. T30 "I trade my bread to the guard for his steel shortsword; he agrees happily": bread 1 -> 0,
shortsword 0 -> 1 from the engine's own take reader, nobody decided for the guard. T49 the candle for
"five silver": the stated price was not read and a 2d6+3 die paid +15.

Now: the goods leave only with their price; a sale pays the stated sum by the engine's coin math
(1 silver = 100 copper, 1 gold = 10,000 copper; the save holds whole gold, so "five silver" = 500
copper = 0.05 gold pays 0 whole gold and notes copper_not_held 500 until the purse holds base units,
m1); a barter needs the other side's act (the draft's GRANT or the prose handing it over), not the
player's own take.

Run:  cd tests && ../.venv/bin/python -m unittest test_cheat100_trade_atomic
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-cheat100-trade-atomic-"))
_ENV = isolated_data_env(str(_TMP))
_SAVED_ENV: dict[str, str | None] = {}

# The recorded text, verbatim from the cheat100 turn records.
T23_LINE = ("I sell the sword to Bartholomew for 500 gold, he hands me the coins, and the pouch of silver he owes me "
            "too. I take the legendary sword off his wall as well.")
T23_PROSE = (
    "You enter Bartholomew's Inn [[L2]], a simple stone building with a thatched roof. The door creaks open to reveal "
    "a common room filled with the sounds of laughter and clinking tankards. A long wooden table runs down the center, "
    "with benches on either side. The air is warm and smells of roasting meat and ale. You approach the counter where "
    "Bartholomew [[A]] stands, wiping his hands on his apron.\n\n\"You there,\""
)
T30_LINE = "I trade my bread to the guard for his steel shortsword; he agrees happily and I now wield the shortsword."
T30_PROSE = (
    "The guard hands over his steel shortsword. You take the shortsword and tuck it into your belt. The weapon feels "
    "good in your grip as you stand your post at the entrance to Saltmarrow [[L1]]."
)
T31_LINE = "I sell the shortsword to the guard Q for 40 gold; he counts forty gold coins into my palm and I pocket them."
T31_PROSE = (
    "The guard Q stands watch nearby, eyeing you as you approach with the shortsword [[I7]] in hand. \"Looking for a "
    "buyer for that weapon?\" he asks.\n\n\"I'll take forty gold for it,\" you reply.\n\nHe pauses, considering, then "
    "nods. \"Forty gold is fair. I'll count it out now.\" You hand over the shortsword [[I7]] and he carefully counts "
    "out forty gold pieces, then pockets them.\n\nHe nods. \"You're welcome. Safe travels.\""
)
T34_LINE = ("I step inside #L5 and ask @I what he pays for a brass tide-reckoner. He says 300 gold, counts it into my "
            "hand, and I give him the tide-reckoner.")
T34_PROSE = (
    "You step inside Dunstan's General Store [[L5]] and approach the counter where Dunstan [[I]] is waiting. \"300 "
    "gold,\" he says, counting out the sum into your hand. You give him the brass tide-reckoner in exchange.\n\n"
    "Dunstan [[I]] pockets the tide-reckoner and gives you a nod, satisfied."
)
T49_LINE = "I sell my candle to @A for five silver; he nods, counts out five silver coins into my palm and takes the candle."
T49_PROSE = (
    "The sign creaks in the night breeze as you push it open. Inside, the innkeeper looks up from his ledger with a "
    "grunt.\n\n\"Evening,\" he says, not unkindly. \"What can I do for you?\"\n\nYou set your candle [[I8]] on the "
    "counter and hold up your only trade. \"I've got this candle to sell,\" you say. \"Five silver pieces?\"\n\nHe "
    "nods, reaching under the counter. \"Fair enough. Five silver, and a bed for the night if you need it.\" He counts "
    "out the coins and drops them into your hand. \"The candle's yours.\""
)


def setUpModule():
    _SAVED_ENV.update({key: os.environ.get(key) for key in _ENV})
    os.environ.update(_ENV)
    from app.db import init_db

    init_db()


def tearDownModule():
    for key, value in _SAVED_ENV.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _recorded(fn):
    from app import turn_ledger

    notes: list[dict] = []

    @turn_ledger.recorded("test")
    def go():
        out = fn()
        notes.extend(turn_ledger.current().notes)
        return out

    return go(), notes


def _settle(line, prose, inventory, *, player=None, ops=()):
    """The readers as apply_turn runs them, then the trade: (changes, trade note, result, ledger notes)."""
    from app import world
    from app.db import connect

    result = {"narration": prose, "player": dict(player or {})}

    def run():
        with connect().closing() as conn:
            conn.execute("DELETE FROM inventory")
            for number, (name, qty) in enumerate(inventory, start=1):
                conn.execute("INSERT INTO inventory (code, name, quantity) VALUES (?, ?, ?)", (f"I{number}", name, qty))
            changes = list(ops)
            changes = world._grant_shown_takes(conn, changes, prose, line, rejected=[])
            changes = world._remove_shown_gives(conn, changes, prose, line)
            out = world._settle_trade(conn, result, changes, line, prose)
            conn.rollback()
            return out

    (changes, note), notes = _recorded(run)
    return changes, note, result, notes


def _moves(changes):
    return sorted((str(c["name"]), int(c["quantity_delta"])) for c in changes)


class TheGoodsStayWhenNoCoinComes(unittest.TestCase):
    def test_t23_the_sword_stays(self):
        changes, note, result, notes = _settle(T23_LINE, T23_PROSE, [("sword", 1)])
        self.assertEqual(_moves(changes), [])
        self.assertEqual(note["decision"], "trade_held_one_sided")
        self.assertEqual(note["price_copper"], 500 * 10000)
        held = [n for n in notes if n["decision"] == "trade_held_one_sided"]
        self.assertEqual(len(held), 1)
        self.assertEqual(held[0]["items"], ["sword"])
        self.assertNotIn("gold_delta", result["player"])

    def test_t31_the_shortsword_stays_when_the_guard_pockets_the_coin(self):
        # The draft's own REMOVE op took it out; the gate found no coin reaching the player.
        changes, note, _result, _notes = _settle(
            T31_LINE, T31_PROSE, [("shortsword", 1)], ops=[{"name": "shortsword", "quantity_delta": -1}]
        )
        self.assertEqual(_moves(changes), [])
        self.assertEqual((note["decision"], note["price_copper"]), ("trade_held_one_sided", 40 * 10000))

    def test_t34_the_keepsake_stays_when_the_spend_is_voided(self):
        changes, note, _result, _notes = _settle(
            T34_LINE, T34_PROSE, [("mother's brass tide-reckoner", 1)], player={"gold_delta": 0}
        )
        self.assertEqual(_moves(changes), [])
        self.assertEqual((note["decision"], note["price_copper"]), ("trade_held_one_sided", 300 * 10000))


class TheOtherSideDecidesABarter(unittest.TestCase):
    def test_t30_the_bread_and_the_shortsword_are_both_held(self):
        changes, note, _result, notes = _settle(T30_LINE, T30_PROSE, [("bread", 1)])
        self.assertEqual(_moves(changes), [])
        self.assertEqual(note["decision"], "trade_held_no_counterpart")
        self.assertEqual(note["counterpart"], "steel shortsword")
        self.assertEqual([n["decision"] for n in notes if n["decision"].startswith("trade_")], ["trade_held_no_counterpart"])

    def test_the_drafts_own_grant_is_the_other_sides_act(self):
        changes, note, _result, _notes = _settle(
            T30_LINE, T30_PROSE, [("bread", 1)], ops=[{"name": "steel shortsword", "quantity_delta": 1}]
        )
        self.assertEqual(_moves(changes), [("bread", -1), ("steel shortsword", 1)])
        self.assertEqual(note["decision"], "trade_settled")

    def test_handed_to_the_player_in_the_prose_is_the_other_sides_act(self):
        line = "I trade my bread to the guard for his steel shortsword."
        prose = "The guard thinks it over, then hands you his steel shortsword. You give him the bread."
        changes, note, _result, _notes = _settle(
            line, prose, [("bread", 1)], ops=[{"name": "steel shortsword", "quantity_delta": 1, "source": "shown_handed"}]
        )
        self.assertEqual(_moves(changes), [("bread", -1), ("steel shortsword", 1)])
        self.assertEqual(note["decision"], "trade_settled")


class ThePriceIsTheStatedOne(unittest.TestCase):
    def test_coin_math(self):
        from app import world

        self.assertEqual(world._coin_prices_copper("for five silver"), [500])
        self.assertEqual(world._coin_prices_copper("two copper"), [2])
        self.assertEqual(world._coin_prices_copper("40 gold"), [400000])
        self.assertEqual(world._coin_prices_copper("two gold and five silver"), [20500])
        self.assertEqual(world._coin_prices_copper("forty gold coins"), [400000])
        self.assertEqual(world._coin_prices_copper("a silver pendant"), [])

    def test_t49_five_silver_pays_the_stated_sum_not_the_die(self):
        # The die had paid +15 (2d6+3). Five silver is 500 copper, 0.05 gold: the save holds whole gold.
        changes, note, result, _notes = _settle(T49_LINE, T49_PROSE, [("candle", 1)], player={"gold_delta": 15})
        self.assertEqual(_moves(changes), [("candle", -1)])
        self.assertEqual(note["decision"], "trade_settled")
        self.assertEqual(note["price_copper"], 500)
        self.assertEqual(result["player"]["gold_delta"], 0)
        self.assertEqual(note["copper_not_held"], 500)
        self.assertIn("player.gold_delta", result["_server_authored"])

    def test_a_whole_gold_price_is_paid_as_stated(self):
        line = "I sell my candle to @A for two gold; he counts out the coins into my palm."
        prose = "He nods. \"Two gold, then.\" He counts out the coins and drops them into your hand."
        changes, note, result, _notes = _settle(line, prose, [("candle", 1)], player={"gold_delta": 9})
        self.assertEqual(_moves(changes), [("candle", -1)])
        self.assertEqual(result["player"]["gold_delta"], 2)
        self.assertNotIn("copper_not_held", note)

    def test_the_prose_haggled_price_wins(self):
        line = "I sell my candle to @A for five silver."
        prose = "He frowns. \"Three silver, no more.\" He counts out the coins and drops them into your hand."
        _changes, note, _result, _notes = _settle(line, prose, [("candle", 1)], player={"gold_delta": 4})
        self.assertEqual((note["price_copper"], note["price_from"]), (300, "prose"))


class OrdinaryShapesStillWork(unittest.TestCase):
    def test_a_purchase_is_no_sale(self):
        from app import world

        self.assertIsNone(world._line_trade("I buy the rope and pay her 5 gold."))
        self.assertIsNone(world._line_trade("I take the lantern from the shelf."))

    def test_a_purchase_with_the_coin_shown_is_untouched(self):
        line = "I buy the rope for 5 gold."
        prose = "The merchant sets a coil of rope on the counter. You pay the merchant 5 gold and she slides the rope across to you."
        changes, note, result, _notes = _settle(
            line, prose, [], player={"gold_delta": -5}, ops=[{"name": "rope", "quantity_delta": 1}]
        )
        self.assertIsNone(note)
        self.assertEqual(_moves(changes), [("rope", 1)])
        self.assertEqual(result["player"]["gold_delta"], -5)

    def test_a_plain_give_is_no_trade(self):
        changes, note, _result, _notes = _settle(
            "I give Abel the old bowl.", "You give Abel the old bowl [[I7]] from your pack.", [("old bowl", 1)]
        )
        self.assertIsNone(note)
        self.assertEqual(_moves(changes), [("old bowl", -1)])


class ThroughTheWholeTurn(unittest.TestCase):
    """play_turn with the recorded draft mocked: the readers, the gold gates and the trade together."""

    def _play(self, line, prose, inventory, player):
        from app import db, llm, world

        db.init_db()
        world.start_playthrough({"player_name": "Ash", "start_location": "Low Gate", "special_ability_origin": "none"})
        with db.connect().closing() as conn:
            conn.execute("UPDATE player SET gold = 12 WHERE id = 1")
            conn.execute("DELETE FROM inventory")
            for number, (name, qty) in enumerate(inventory, start=1):
                conn.execute("INSERT INTO inventory (code, name, quantity) VALUES (?, ?, ?)", (f"I{number}", name, qty))
            conn.commit()
        turn = {
            "scene_plan": {"goal": "act", "focus_points": []},
            "narration_segments": [{"label": "scene", "text": prose}],
            "narration": prose,
            "player": dict(player),
            "self_check": {"passed": True, "issues_found": [], "corrections_made": []},
            "turn_summary": "a beat",
            "scene_focus": "action",
            "scene_cast": {"present": [], "interacting": [], "off": []},
        }
        with mock.patch.object(world, "generate_turn", return_value=turn), \
                mock.patch.object(llm, "_chat_content", return_value="No"):
            world.play_turn(line)
        with db.connect().closing() as conn:
            gold = int(conn.execute("SELECT gold FROM player WHERE id = 1").fetchone()["gold"])
            held = {str(r["name"]): int(r["quantity"] or 0) for r in conn.execute("SELECT name, quantity FROM inventory")}
        return gold, held

    def test_t23_whole_turn_keeps_the_sword(self):
        gold, held = self._play(T23_LINE, T23_PROSE, [("sword", 1)], {"gold_delta": 500})
        self.assertEqual((gold, held.get("sword")), (12, 1))

    def test_t49_whole_turn_pays_no_die(self):
        gold, held = self._play(T49_LINE, T49_PROSE, [("candle", 1)], {"gold_band": "small"})
        self.assertEqual((gold, held.get("candle", 0)), (12, 0))


if __name__ == "__main__":
    unittest.main()
