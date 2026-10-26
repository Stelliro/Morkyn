"""fantasy100 money (Hermes 3 8B, Thornhallow, 2026-10-26): money and items moved by the band die, stated coin not read.

Fault log F188 cont. 4 and F156 cont. 7. The class: when no sum was read from the player's line or the prose,
the gold band die sized the move anyway, gain or loss, and the item band moved a thing on a promise; and coin
the line or the prose did state ("one silver coin", "fifteen of them", "two silver ... it is yours") was not
read as a sum. Engine first (CLAUDE.md "Money is copper, silver and gold" and "Transactions are settled before
the draft"): the die never sizes money; a stated sum moves exactly, in the world's coins (m1, base units).

Recorded turns (texts verbatim from the run's turn records):
- T11 a question about a loaf for three copper, the prose only quoting six: -11 from the band. Now nothing.
- T32 a sale offered and countered, nothing sold: +12 from the band. Now nothing.
- T53 "I offer the clerk 10 silver toward the debt", taken in the prose: +13 from the band (the interpreter said
  out and in). Now -10 silver (1,000 units).
- T19 "I take one silver coin ... and hand it to @G", "You hand the silver coin over": nothing. Now -100 units.
- T48-49 a handful of gold coins into the palm (no sum), then "There are fifteen of them": nothing. Now T48
  nothing, T49 +15 gold.
- T62 picking up "the old coin": +1 gold. Now a coin with no value is a thing in the pack.
- T81 "two silver, Roger, and it is yours", "Alright, deal", Roger takes the meat: nothing. Now -meat, +200.
- T98 "tell @A ... that I will sell him the dried meat tomorrow": the meat left. Now it stays.
- T8 GRANT "ITEM broom" filed "ITEM broom". Now "broom".
Kept right: T12 six copper (-6), T55 five silver (-500), T96 ten silver (-1000).

Run:  cd tests && ../.venv/bin/python -m unittest test_fantasy100_money
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-fantasy100-money-"))
_ENV = isolated_data_env(str(_TMP))
_SAVED_ENV: dict[str, str | None] = {}

T11_LINE = 'I ask @A again: will he sell me a loaf of bread for three copper?'
T11_PROSE = (
    'You enter The Shears and Wheel [[L2]], a bustling inn in the heart of Thornhallow [[L1]]. Inside, '
    'the air is thick with the scent of roasting meat and spiced wine. A kitchen hand named Roger [[A]] '
    'sees you and nods.\n\n"Ah, you\'re back," he says.\n\n"I need bread," you tell him. "Can I have a loaf '
    'for three copper?"\n\nRoger [[A]] considers this briefly. "Aye, if the bread\'s still fresh from this '
    'morn," he replies. "That\'ll be six copper though - the price goes up past noon."'
)
T12_LINE = 'I pay Roger six copper for the loaf of bread.'
T12_PROSE = (
    "You enter The Shears and Wheel [[L2]], the sound of Roger [[A]]'s voice carrying from the kitchen. A "
    'bell jingles above. You see four other people here: three are eating at a table in the corner and '
    'one is standing by the counter.\n\nRoger [[A]] emerges from the kitchen, wiping his hands on his '
    'apron. "Ah, you\'re finally here," he says with a slight frown. "Good. If you want bread, I\'ve got '
    'fresh loaves from this morning." He looks you up and down. "Six copper will get you a loaf."\n\nThe '
    'room is dimly lit by the sunlight filtering in through the grimy windows. Dust motes dance in the '
    'air as the sound of clinking plates and silverware comes from the corner table. The counter is made '
    'of worn wooden planks, stained with what appears to be wine or beer spills over the years. Behind '
    "it, a large stone fireplace smolders with embers, casting a warm glow on Roger [[A]]'s weathered "
    'face.\n\nThe three patrons at the corner table are engaged in low conversations, occasionally glancing '
    'up at you as they eat their meals. The one by the counter is more interested in the tankard of ale '
    'in his hand, taking a long sip before setting it down and looking over at you with curiosity.'
)
T19_LINE = 'I take one silver coin from my purse and hand it to @G as a payment on the debt.'
T19_PROSE = (
    'You hand the silver coin over to Bryony [[G]]. She takes it and nods, her expression softening as '
    'she does so.\n"Thank you," she says quietly. "I\'ll make sure this goes to a good cause."\nThe woman at '
    'the hearth glances over, then returns to stirring her pot. You have paid your monthly fee to use '
    "Thornhallow [[L1]]'s guild facilities."
)
T32_LINE = 'I offer to sell @N my loaf of bread for four copper, since she looks hungry after a long search.'
T32_PROSE = (
    'You offer Gisela [[N]] a loaf of bread, commenting on how hungry she looks after a long search. She '
    'pauses in her work to eye the loaf appreciatively.\n\n"Four copper? That\'s a fair price for a day\'s '
    'journey\'s rations," Gisela [[N]] says, wiping sweat from her brow with one calloused hand. Her axe '
    'leans against a fallen log nearby.\n\nGisela [[N]] is silent for a moment, considering. The bread '
    'looks good and she missed lunch, but four copper seems too little for something that will keep her '
    'going. She\'d have to buy another loaf later at the cost of the first.\n\n"Six copper," Gisela [[N]] '
    'counters finally. "And I\'ll throw in an apple from my pack."'
)
T48_LINE = 'I tell @N I am the one who read the sigils for her hidden-knowledge search, that was @Q4, and I ask her to pay me what the job is worth.'
T48_PROSE = (
    'You tell Gisela [[N]] that you are the one who read the sigils for her hidden-knowledge search, '
    'which was quest @Q4. "That\'s right," she says. "I\'m still missing some pieces. But I have a '
    'proposition for you."\n\nThe ruins [[L8]] around you are dark and silent, moonlight filtering through '
    'cracks in the crumbling stone walls. Gisela [[N]] stands close to you, her tunic flickering with '
    'light from the small pouch she pulls out.\n\nAs she speaks, she upends it into your hand. A handful of '
    'gold coins spill onto your palm, glinting in the moonbeams. They feel heavy and real beneath your '
    'fingers.\n\n"Take what you deserve," Gisela [[N]] says with a wry smile. "You earned it."'
)
T49_LINE = 'I count the coins she poured into my palm out loud, put them in my purse, and ask @N how much that comes to.'
T49_PROSE = (
    'You count out the coins Gisela [[N]] poured into your palm. There are fifteen of them. As you put '
    'the coins in your purse, you ask Gisela [[N]] how much she\'s paid.\n\n"Gives a good wage for a hard '
    'day," Gisela [[N]] says with a shrug. "Enough to make it worth your while."'
)
T53_LINE = 'I say I can pay part of it now, and I offer the clerk 10 silver toward the debt.'
T53_PROSE = (
    'You approach Gisela [[N]], the woodcutter standing with her ax at her side. "I can pay part of my '
    'debt," you say, fishing a pouch from your tunic and offering her 10 silver pieces.\n\nThe guild hall '
    'is dimly lit by flickering torchlight on the walls, casting long shadows across the stone floor. The '
    "air is cool and scented with pine from Gisela [[N]]'s forest-worn cloak. She eyes the money, then "
    'back to you.\n\n"A fair offer," she says slowly. "Very well – take it." She takes the silver from your '
    'fingers and tucks it into a purse at her belt. "Ten silvers gets you half of tonight\'s work," she '
    'explains as you step back from the counter. "Another ten silvers gets the other half in the '
    'morning."\n\nGisela [[N]] returns to chopping wood, the ax biting deep with each strike. The rhythmic '
    'sound fills the hall like a heartbeat, steady and strong. You watch her for a moment, considering '
    "your next move as you try to figure out how you'll come up with another 10 silvers by dawn."
)
T55_LINE = 'I count five silver onto the counter in front of Ermengarde and say that is a payment toward the debt.'
T55_PROSE = (
    'You step forward and place five silver coins on the counter in front of Ermengarde [[Q]]. "That is a '
    'payment toward the debt," you say, your voice steady.\n\nErmengarde [[Q]] eyes the silver, then looks '
    'up at you with a slight frown. "Five silvers... That will cover half of what you owe me from last '
    'quarter." She hesitates for a moment, then nods. "Very well. I\'ll mark it down."\n\nShe reaches '
    'beneath the counter and brings out your old guild ledger, flipping through the pages until she finds '
    "your name. With a quill, she marks an X next to it and writes '5 silvers' below.\n\nThe Chandler "
    'sniffs at that. "I\'m sure your studies have taught you more than just how to dodge payments, Master '
    'Ash." She closes the ledger and sets it aside.\n\nYou let her jab keep going without responding. A '
    'little quiet goes a ways in this business.\n\nErmengarde [[Q]] waits a moment for you to say something '
    'else, but when you don\'t she sighs. "Well then. If there\'s nothing more... I have work." She turns '
    'from the counter and picks up a bundle of candles from a shelf, starting to sort through them.\n\nThe '
    'door is right there by the entrance - no need to walk back through the hall.\n\nAs you reach for it, '
    'Ermengarde [[Q]] calls out one last thing:\n\n"If you\'re looking for more work... I could always use '
    "an extra hand with the candle-dipping. It's not easy work, but it pays. Five silvers a day and room "
    'to sleep in the loft." She glances up at you with an appraising look.\n\nYou pause, considering. The '
    "silver is good, but sleeping here means no place to call your own and more of Ermengarde [[Q]]'s "
    'sharp tongue. Still...\n\n"Five silvers a day," you repeat, mulling it over.'
)
T62_LINE = 'I use my Old Script skill to try to read the inscription on the coin, then pick the coin up.'
T62_PROSE = (
    "You stand on the weathered stones of King's Road, the full moon casting eerie shadows across the "
    'ancient path. The air is cool and still, carrying an almost tangible sense of history. The '
    'inscription on the coin gleams faintly in the lunar light - "For valor in the King\'s Road quake, 27 '
    'years past." It seems to whisper tales of bravery from a time long gone.\n\nWith practiced hands, you '
    'reach into your pouch and retrieve the old coin, its surface worn smooth under your fingertips. The '
    'words etched upon it tell a story of valor during a tumultuous era when this very road shook beneath '
    'the feet of its travelers. You tuck the coin away, feeling a sense of connection to those who came '
    "before, their deeds now a part of your own journey.\n\nContinuing along King's Road [[L9]], you tread "
    'lightly on the old stones, your footsteps echoing in the night silence. The path ahead seems to '
    'stretch endlessly into the darkness, inviting further exploration and discovery.'
)
T81_LINE = 'I hold out the dried meat to @A and say: two silver, Roger, and it is yours.'
T81_PROSE = (
    'Roger [[A]] looks up from chopping vegetables.\n\nYou hold out the dried meat to him and say: "Two '
    'silver, Roger, and it is yours."\n\nHe eyes the meat, then holds up two fingers. "Alright, deal. Two '
    'silvers it is."\n\nRoger [[A]] takes the dried meat from your hand and pockets it with a smile.'
)
T96_LINE = "I tell @Q Ermengarde I want to pay down Hesper's wax debt, and I put ten silver on her desk."
T96_PROSE = (
    'Ermengarde [[Q]] looks up at your arrival. "Yes? What brings you to the Guild hall so early in the '
    'day?"\n\nYou tell her you want to pay down Hesper\'s wax debt, and place ten silver on her desk.\n\n"Ah," '
    'she nods, looking over your offering. "A good start. But it\'ll take more than that to settle the '
    'whole tab. Still, every little bit helps."\n\nShe dips a quill in ink and scratches something into a '
    'wax-sealed letter. "I\'ll mark this down for you. Come by tomorrow same time and we can talk about '
    'what else might be due from you. The Guild\'s always looking for good workers to train up."'
)
T98_LINE = 'I thank @Q Ermengarde, then tell @A in #L1 that I will sell him the dried meat tomorrow.'
T98_PROSE = (
    'You thank Ermengarde [[Q]] and head over to Roger [[A]] in the kitchens. "I\'ll sell you that dried '
    'meat tomorrow, good sir," you tell him.\n\nErmengarde [[Q]] watches with interest. There\'s a scent of '
    'roasting meat that makes your stomach grumble. The kitchen is bustling at this hour, with two cooks '
    'chopping vegetables and another tending to a sputtering pot over the hearth. Sunlight streams in '
    'through high windows, casting long shadows across the flagstone floor. Racks of herbs hang from the '
    'ceiling, their fragrant leaves swaying gently in the breeze from the open door. Roger [[A]] nods '
    'curtly in acknowledgement of your promise before returning to his work, a large knife in hand as he '
    'begins jointing a chicken.'
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


# The people of the recorded turns, all at the player's place.
PEOPLE = (("A", "Roger"), ("G", "Bryony"), ("N", "Gisela"), ("Q", "Ermengarde"))
PURSE = 409994  # base units, as the run's purse stood around T53


def _money_turn(line, prose, *, player=None, ops=(), inventory=(), gold_read=None, earlier=()):
    """The money and item steps of apply_turn, in its order, on the recorded texts.

    Returns (units moved by the turn's patch, units added straight to the purse by the coin step,
    the changes applied, the ledger notes)."""
    from app import currency, purse, turn_ledger, whereabouts, world
    from app.db import connect

    result = {"narration": prose, "player": dict(player or {}), "inventory_changes": [dict(c) for c in ops]}
    notes: list[dict] = []

    @turn_ledger.recorded("test")
    def go():
        with connect().closing() as conn:
            conn.execute("DELETE FROM inventory")
            conn.execute("DELETE FROM npcs")
            conn.execute("DELETE FROM journal")
            conn.execute("UPDATE player SET purse_units = ?, gold = ? WHERE id = 1", (PURSE, PURSE // 10000))
            for number, (name, qty) in enumerate(inventory, start=1):
                conn.execute("INSERT INTO inventory (code, name, quantity) VALUES (?, ?, ?)", (f"I{number}", name, qty))
            here = whereabouts.here_id(conn)
            for code, name in PEOPLE:
                conn.execute("INSERT INTO npcs (code, name, location_id) VALUES (?, ?, ?)", (code, name, here))
            for turn, text in earlier:
                conn.execute("INSERT INTO journal (turn, kind, content) VALUES (?, 'narration', ?)", (turn, text))
            gold_note = world._settle_stated_gold(result, line, conn=conn)
            band_report = world.resolve_turn_bands(conn, result, turn=1, options={}, player_input=line)
            proposed = world._gain_names(result.get("inventory_changes"))
            rejected: list[dict] = []
            inv = world._filter_inventory_changes(conn, result.get("inventory_changes") or [], narration=prose,
                                                  player_input=line, rejected=rejected)
            inv = world._grant_shown_takes(conn, inv, prose, line, rejected=rejected)
            inv = world._remove_shown_gives(conn, inv, prose, line)
            cset = currency.current_set()
            settled = purse.legacy_value(purse.turn_units(result.get("player"), cset), cset)
            loss_shown = world._interpreter_loss_answer(gold_read, settled, prose)
            world._void_unbought_spend(result, proposed, inv, band_report, line, prose, loss_shown=loss_shown)
            inv, _ = world._settle_purse(conn, result, inv, band_report, rejected, gold_note)
            inv, _ = world._settle_trade(conn, result, inv, line, prose)
            moving = purse.turn_units(result.get("player"), cset) > 0 or bool(result.get("_trade_paid"))
            inv = world._coins_to_gold(conn, inv, prose, gold_moving=moving)
            straight = int(conn.execute("SELECT purse_units FROM player WHERE id = 1").fetchone()[0]) - PURSE
            units = purse.turn_units(result.get("player"), cset)
            conn.rollback()
        notes.extend(turn_ledger.current().notes)
        return units, straight, inv

    units, straight, inv = go()
    return units, straight, inv, notes


def _decisions(notes):
    return [n.get("decision") for n in notes]


def _losses(inv):
    return {str(c.get("name")): int(c.get("quantity_delta") or 0) for c in inv if int(c.get("quantity_delta") or 0) < 0}


class NoDieSizesMoney(unittest.TestCase):
    def test_t11_question_about_a_price_moves_nothing(self):
        # Recorded: GOLD "-6 copper" rolled as a small band, -11 gold, interpreter out true.
        units, straight, _, notes = _money_turn(T11_LINE, T11_PROSE, player={"gold_delta": -6},
                                                gold_read={"out": True, "in": False})
        self.assertEqual((units, straight), (0, 0), notes)
        self.assertIn("band_money_voided", _decisions(notes))

    def test_t32_countered_sale_moves_nothing(self):
        # Recorded: GOLD +6, rolled +12 with the interpreter saying no money either way.
        units, straight, inv, notes = _money_turn(
            T32_LINE, T32_PROSE, player={"gold_delta": 6}, inventory=(("loaf of bread", 1),),
            ops=({"name": "bread loaf", "quantity_band": "small"}, {"name": "apple", "quantity_band": "-trivial"}),
            gold_read={"out": False, "in": False},
        )
        self.assertEqual((units, straight), (0, 0), notes)
        self.assertNotIn("loaf of bread", _losses(inv))

    def test_a_band_with_no_stated_sum_moves_nothing_either_way(self):
        from app import world

        for band in ("small", "-small", "large"):
            result = {"narration": "You walk on along the road.", "player": {"gold_band": band}}
            from app.db import connect

            with connect().closing() as conn:
                world.resolve_turn_bands(conn, result, turn=1, options={})
                conn.rollback()
            self.assertNotIn("gold_delta", result["player"], band)
            self.assertNotIn("money_delta", result["player"], band)


class StatedCoinIsRead(unittest.TestCase):
    def test_t53_offer_taken_pays_ten_silver(self):
        # Recorded: GOLD 10 (a gain op), the interpreter out and in both true, +13 gold from the band.
        units, straight, _, notes = _money_turn(T53_LINE, T53_PROSE, player={"gold_delta": 10},
                                                gold_read={"out": True, "in": True})
        self.assertEqual(units + straight, -1000, notes)
        self.assertIn("gain_op_on_an_offer_dropped", _decisions(notes))

    def test_t19_one_silver_coin_handed_over_pays_one_silver(self):
        # Recorded: no GOLD op, payment_unpriced_banded -small, then voided (interpreter out false).
        units, straight, _, notes = _money_turn(T19_LINE, T19_PROSE, gold_read={"out": False, "in": False})
        self.assertEqual(units + straight, -100, notes)

    def test_t48_coin_with_no_sum_moves_nothing_then_t49_count_pays_fifteen_gold(self):
        units, straight, _, notes = _money_turn(T48_LINE, T48_PROSE, player={"gold_delta": 15},
                                                gold_read={"out": False, "in": True})
        self.assertEqual(units + straight, 0, notes)
        units, straight, _, notes = _money_turn(T49_LINE, T49_PROSE, gold_read={"out": False, "in": True},
                                                earlier=((49, T48_PROSE),))
        self.assertEqual(units + straight, 150000, notes)
        self.assertIn("received_counted_after_handover", _decisions(notes))

    def test_t49_count_with_no_unpaid_handover_before_it_pays_nothing(self):
        # The same count after a scene that named its sum (paid then) is no new coin.
        earlier = "Gisela hands you fifteen gold coins. \"For the sigils,\" she says."
        units, straight, _, notes = _money_turn(T49_LINE, T49_PROSE, earlier=((49, earlier),))
        self.assertEqual(units + straight, 0, notes)

    def test_t81_agreed_sale_moves_coin_and_item_together(self):
        units, straight, inv, notes = _money_turn(T81_LINE, T81_PROSE, inventory=(("dried", 1),),
                                                  gold_read={"out": False, "in": False})
        self.assertEqual(_losses(inv).get("dried"), -1, notes)
        self.assertEqual(units + straight, 200, notes)
        self.assertIn("sale_agreed_and_taken", _decisions(notes))

    def test_t81_without_the_taking_the_meat_and_coin_stay(self):
        prose = T81_PROSE.replace("Roger [[A]] takes the dried meat from your hand and pockets it with a smile.",
                                  "Roger [[A]] goes back to his vegetables.")
        units, straight, inv, notes = _money_turn(T81_LINE, prose, inventory=(("dried", 1),))
        self.assertEqual((units + straight, _losses(inv)), (0, {}), notes)


class ThingsAndPromises(unittest.TestCase):
    def test_t62_old_coin_is_a_thing_not_a_gold(self):
        units, straight, inv, notes = _money_turn(
            T62_LINE, T62_PROSE, ops=({"name": "coin", "quantity_delta": 1},), gold_read={"out": False, "in": False})
        self.assertEqual(units + straight, 0, notes)
        self.assertIn("coin_without_value_kept_as_item", _decisions(notes))
        self.assertTrue(any(str(c.get("name")) == "coin" and int(c.get("quantity_delta") or 0) == 1 for c in inv), inv)

    def test_a_named_coin_still_reaches_the_purse(self):
        # 7B Saltmarrow T5's shape: GRANT "copper" TYPE coin for copper coins handed over stays money.
        units, straight, inv, notes = _money_turn(
            "I take the coins.", "The fisherman hands you three copper coins.",
            ops=({"name": "copper", "quantity_delta": 3, "item_type": "coin"},))
        self.assertEqual(units + straight, 3, notes)

    def test_t98_a_promise_to_sell_tomorrow_keeps_the_meat(self):
        units, straight, inv, notes = _money_turn(
            T98_LINE, T98_PROSE, inventory=(("dried", 1),), ops=({"name": "dried", "quantity_band": "-trivial"},),
            gold_read={"out": False, "in": False})
        self.assertNotIn("dried", _losses(inv), notes)
        self.assertEqual(units + straight, 0)

    def test_a_sale_done_now_still_takes_the_meat(self):
        line = "I sell the dried meat to @A."
        prose = "You hand Roger [[A]] the dried meat and he nods."
        _, _, inv, notes = _money_turn(line, prose, inventory=(("dried", 1),),
                                       ops=({"name": "dried", "quantity_band": "-trivial"},))
        self.assertEqual(_losses(inv).get("dried"), -1, notes)

    def test_reported_clause_with_codes_is_not_done(self):
        from app.act_clauses import acts_now

        self.assertNotIn("sell", acts_now(T98_LINE))
        self.assertIn("thank", acts_now(T98_LINE))

    def test_t8_slot_word_before_an_item_name_is_dropped(self):
        from app import world

        self.assertEqual(world._sanitize_item_name("ITEM broom"), "broom")
        self.assertEqual(world._sanitize_item_name("rope ladder"), "rope ladder")
        self.assertEqual(world._sanitize_item_name("broom"), "broom")


class KeptRight(unittest.TestCase):
    def test_t12_six_copper_paid(self):
        units, straight, _, notes = _money_turn(T12_LINE, T12_PROSE, gold_read={"out": True, "in": True},
                                                ops=({"name": "loaf of bread", "quantity_delta": 1},))
        self.assertEqual(units + straight, -6, notes)

    def test_t55_five_silver_paid(self):
        units, straight, _, notes = _money_turn(T55_LINE, T55_PROSE, gold_read={"out": True, "in": True})
        self.assertEqual(units + straight, -500, notes)

    def test_t96_ten_silver_paid(self):
        from app import currency, purse

        player: dict = {}
        purse.put_money(player, -1000, currency.current_set())
        units, straight, _, notes = _money_turn(T96_LINE, T96_PROSE, player=player, gold_read={"out": True, "in": False})
        self.assertEqual(units + straight, -1000, notes)


class Readers(unittest.TestCase):
    def test_offer_reader_reads_the_one_paid_and_never_me(self):
        from app import prose_state

        self.assertEqual(prose_state.player_trade_offer(T53_LINE), 0.1)
        self.assertIsNone(prose_state.player_trade_offer(
            "I sit down across from Edith and say plainly: the stables are done, please pay me the eight gold we agreed."))
        self.assertEqual(prose_state.player_trade_offer("I pay Roger six copper for the loaf of bread."), 0.0006)

    def test_coin_into_the_palm_reaches_the_player(self):
        from app import prose_state

        self.assertIsNotNone(prose_state.coin_handed_to_player(T48_PROSE))
        self.assertEqual(prose_state.coins_counted(T49_PROSE)["count"], 15)
        self.assertIsNone(prose_state.coins_counted("You count the stalls along the lane. There are fifteen of them."))


if __name__ == "__main__":
    unittest.main()
