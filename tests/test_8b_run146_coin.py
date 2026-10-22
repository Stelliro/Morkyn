"""8B run 146, T73, T76, T77: compound sums, a payment over a gain op, a pointed-at place, a name asked after.

T73: "You count forty-six gold out of your purse into Veyra's palm" came with
GOLD +moderate; "forty-six" read as "six", and the purse grew by 38. Tens and
units together are one number, and a payment the narration shows beats a gain
op. T73 also minted "And Veyra" from a sentence-opening conjunction.

T76: "a narrow passage that leads to the Edge of the Flats [[L8]]" kept a MOVE
there while the player had walked into the Old Wharf: a place named only as
where a path leads is not reached.

T77: "ask the nearest dockhand where Elara Veyne can be found" rolled
persuasion against Elara, who was not there.

Run:  .venv\\Scripts\\python -m unittest tests.test_8b_run146_coin
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import prose_state  # noqa: E402
from app.skill_checks import infer_check_from_action  # noqa: E402
from app.world import _introduced_people, _place_only_pointed_at, _settle_stated_gold  # noqa: E402

PAID = ("You count forty-six gold out of your purse into Veyra’s palm, coin by coin, and speak: “Then I walk.” "
        "The spymaster’s fingers close around the coins, her dark eyebrows knitting together.")


class CompoundSumsAreOneNumber(unittest.TestCase):
    def test_forty_six_is_forty_six(self):
        self.assertEqual(prose_state._number("forty-six"), 46)
        self.assertEqual(prose_state._number("twenty one"), 21)
        self.assertEqual(prose_state._number("ninety"), 90)
        self.assertIsNone(prose_state._number("forty-forty"))

    def test_the_payment_is_read_whole(self):
        self.assertEqual(prose_state.stated_coin_amounts(PAID)["paid"], [46])
        self.assertEqual(prose_state.coin_mentions(PAID), [46])


class APaymentShownBeatsAGainOp(unittest.TestCase):
    def test_the_purse_loses_what_the_prose_pays(self):
        result = {"narration": PAID, "player": {"gold_band": "moderate"}}
        line = "I count forty-six gold out of my purse into Veyra's hand, coin by coin."
        note = _settle_stated_gold(result, line)
        self.assertEqual(result["player"].get("gold_delta"), -46, note)
        self.assertNotIn("gold_band", result["player"])

    def test_the_players_own_coin_backs_no_gain(self):
        # T71: "counting the gold in your purse ... close to forty-six"; T79: "the memory of forty-six gold coins spent".
        for prose in (
            "You hold your ground, counting the gold in your purse, knowing the number is close to forty-six. Still, the coin in your hand is a promise.",
            "Veyra Drowned’s name lingers, a ghost of debt, and the memory of forty-six gold coins spent on a walk back that felt like a lifetime.",
        ):
            result = {"narration": prose, "player": {"gold_band": "moderate"}}
            note = _settle_stated_gold(result, "I wait.")
            self.assertEqual((note or {}).get("source"), "gain_without_coin_dropped", prose)
            self.assertNotIn("gold_band", result["player"])

    def test_coin_counted_the_turn_after_the_pay_backs_no_second_gain(self):
        # 8B run 147, T48: counting the silver already paid backed GOLD +30.
        prose = ("You count the silver pieces in Reeve Dunmere's open palms, the weight of forty-five a stark reminder of the "
                 "debts you carry. You name the number aloud, the clink of coin echoing between the ruins.")
        result = {"narration": prose, "player": {"gold_band": "moderate"}}
        note = _settle_stated_gold(result, "I count what he put in my palm and say the number aloud.")
        self.assertEqual((note or {}).get("source"), "gain_without_coin_dropped", note)

    def test_a_sum_only_mentioned_backs_no_stated_gain(self):
        # 8B run 147, T92: "the weight of the eleven gold coins hangs in the damp morning" backed GOLD 11.
        prose = ("Mira Venn stands at the board, her fingers tracing the names of those who owe the guild. The guild has "
                 "posted your name, and the weight of the eleven gold coins hangs in the damp morning. You hold your ground.")
        result = {"narration": prose, "player": {"gold_delta": 11}}
        _settle_stated_gold(result, "\"Eleven gold, now, into my hand.\"")
        self.assertNotEqual(result["player"].get("gold_delta"), 11)

    def test_the_players_own_ask_told_back_backs_no_gain(self):
        # 8B run 148, T34: "ask him to ... pay the forty-five gold" in the narration backed GOLD 45 while Roderic refused.
        prose = ("You tell him the salvage from the Stormbreaker is on the carts, fittings, chain, and planks, and ask him to mark "
                 "the job as complete and pay the forty-five gold. He exhales sharply. \"The salvage crew's already taken what they "
                 "wanted. The rest is for the reeve's men.\"")
        line = "I tell Roderic the Stormbreaker's salvage is on the carts and ask him to mark the guild's job done and pay the forty-five gold."
        result = {"narration": prose, "player": {"gold_delta": 45}}
        _settle_stated_gold(result, line)
        self.assertNotEqual(result["player"].get("gold_delta"), 45)

    def test_coin_handed_to_the_player_still_gains(self):
        prose = "He counts out twenty gold into your palm. “For the warning,” he says."
        result = {"narration": prose, "player": {"gold_delta": 20}}
        _settle_stated_gold(result, "I hold out my hand.")
        self.assertEqual(result["player"].get("gold_delta"), 20)


class APurchaseWithNoPriceStillCosts(unittest.TestCase):
    """8B run 147, T20 and T21: goods bought and coins tossed into a palm moved no gold."""

    def test_goods_bought_with_no_sum_roll_a_small_spend(self):
        prose = ("You arrive at the market square. The lantern you bought is heavy in your satchel, and the rope is coiled "
                 "tightly, ready for the task ahead.")
        result = {"narration": prose, "player": {},
                  "inventory_changes": [{"name": "Lantern", "quantity_band": "small"}, {"name": "Rope", "quantity_band": "small"}]}
        note = _settle_stated_gold(result, "I walk back up into Saltmarrow to buy a lantern and a length of rope before the tide.")
        self.assertEqual(result["player"].get("gold_band"), "-small", note)

    def test_coins_tossed_into_a_palm_are_a_payment(self):
        prose = ("He rummages through a pouch. When he finally pulls out a handful of silver, he mutters about the tides. "
                 "You count the coins, then toss them into his palm. He nods, grumbling about debts.")
        result = {"narration": prose, "player": {}}
        _settle_stated_gold(result, "I ask the stallholder who sold me the lantern and rope what I owe, and pay it from my purse.")
        self.assertEqual(result["player"].get("gold_band"), "-small")

    def test_a_gain_op_on_the_players_own_purchase_is_a_spend(self):
        # 8B run 147, T62: GOLD +small on buying a meal and a bed grew the purse by 8.
        prose = ("You make your way to the counter. He slides a mug of ale towards you. He returns with a plate of stew and a "
                 "loaf of bread. The barkeep nods, signaling that your stay is paid for, and you rise from your chair.")
        result = {"narration": prose, "player": {"gold_band": "small"}}
        note = _settle_stated_gold(result, "I walk back into Saltmarrow and go into the Stag and Heron to buy a hot meal and a bed for the night.")
        self.assertEqual(result["player"].get("gold_band"), "-small", note)

    def test_asking_who_pays_is_no_payment_by_the_player(self):
        # 8B run 148, T9: "how much coin the load pays and who pays it" flipped a model gain into a spend.
        prose = ("You ask how much the load pays and who pays it. \"Thirty gold,\" he says, \"from the Harbour Reeve. He's the "
                 "one who wants the fish.\" You turn toward the wharf.")
        result = {"narration": prose, "player": {"gold_delta": 30}}
        note = _settle_stated_gold(result, "I ask Roderic how much coin the load pays and who pays it, then go to find the Mistral.")
        self.assertNotEqual((note or {}).get("source"), "purchase_gain_flipped", note)
        self.assertNotEqual(result["player"].get("gold_delta"), -30)
        self.assertNotEqual(result["player"].get("gold_delta"), 30)

    def test_coin_that_moves_to_someone_else_backs_no_gain(self):
        # 8B run 152f, T7: Garrick "idly tossing a coin into the water" backed GOLD +small, rolled to +10.
        prose = ("You push the loaded wagon along the dock. The sailor, Garrick [[D]], leans on his crate, idly tossing a "
                 "coin into the water. You wheel the wagon inside the warehouse.")
        result = {"narration": prose, "player": {"gold_band": "small"}}
        note = _settle_stated_gold(result, "I push the cart along the dock to Warehouse 7.")
        self.assertEqual((note or {}).get("source"), "gain_without_coin_dropped", note)

    def test_a_jobs_pay_described_backs_no_gain(self):
        # 8B run 148, T8: "it's not much, but it pays in coin" let GOLD +small stand on the offer.
        prose = ("\"There's a load of fish in the hold of the Mistral,\" he says. \"It's not much, but it pays in coin. You'll "
                 "have to haul it yourself, though.\" He sighs, the sound heavy with the weight of the day's toil.")
        result = {"narration": prose, "player": {"gold_band": "small"}}
        note = _settle_stated_gold(result, "I ask whether there is a day's hauling on these boats that pays coin tonight.")
        self.assertEqual((note or {}).get("source"), "gain_without_coin_dropped", note)

    def test_paying_for_a_bed_with_a_gain_op_is_a_spend(self):
        # 8B run 148, T17: "pay for a bed, and sleep" with GOLD 30 left the purse unchanged.
        prose = ("The innkeeper nods at your request. You pay with a handful of coins, the sound of them clinking in the wooden "
                 "bowl a reminder of your dwindling funds. You are given a small bed.")
        result = {"narration": prose, "player": {"gold_delta": 30}}
        note = _settle_stated_gold(result, "I am dead on my feet; I go to the Stag and Heron, pay for a bed, and sleep until morning.")
        # No price named anywhere: the spend is a rolled small amount, not the model's thirty.
        self.assertEqual(result["player"].get("gold_band"), "-small", note)
        self.assertNotIn("gold_delta", result["player"])

    def test_paying_a_person_for_a_meal_with_a_gain_op_is_a_small_spend(self):
        # 8B run 148, T45: "pay Eldric for them" with GOLD 30 grew the purse by a rolled 39.
        prose = ("You order the fish and a mug of ale, pay Eldric for them, and let the matter of the stranger drop for now. "
                 "The ale is warm and the fish is fresh, though the bread is stale. You sit by the fire.")
        result = {"narration": prose, "player": {"gold_delta": 30}}
        note = _settle_stated_gold(result, "I order the fish and a mug of ale, pay Eldric for them, and let the matter of the stranger drop for now.")
        self.assertEqual((note or {}).get("source"), "purchase_gain_flipped", note)
        self.assertEqual(result["player"].get("gold_band"), "-small", note)

    def test_coin_handed_over_at_a_named_price_is_paid(self):
        # 8B run 148, T68: GOLD 10 (a gain) on "You hand over the coin" at "ten gold for the rope and mallet" was dropped to nothing.
        prose = ("You reach for a coil of rope and a mallet. You ask for his name and price. “Name’s Ulric,” he says. “The "
                 "price’s ten gold for the rope and mallet. That’s the going rate.” You hand over the coin, and he hands over "
                 "the items. The transaction is quick.")
        result = {"narration": prose, "player": {"gold_delta": 10}}
        note = _settle_stated_gold(result, "I go to the crates and take a coil of rope and a mallet, then ask the scarred man his name and his price.")
        self.assertEqual(result["player"].get("gold_delta"), -10, note)

    def test_a_sum_said_as_the_coin_is_handed_over_beats_the_band(self):
        # 8B run 149, T37: "tosses it to you. 'Forty-five gold,' she says" with GOLD +moderate paid a rolled 41.
        prose = ("She pulls a small pouch from her belt and tosses it to you. \"Forty-five gold,\" she says, her tone flat. "
                 "\"That’s for the first.\" You catch the pouch, the coins clinking inside.")
        result = {"narration": prose, "player": {"gold_band": "moderate"}}
        note = _settle_stated_gold(result, "\"Salvage, then. Hand over what the guild offers for the two boxes, Lettice.\"")
        self.assertEqual(result["player"].get("gold_delta"), 45, note)
        self.assertNotIn("gold_band", result["player"])

    def test_a_named_price_on_a_purchase_is_the_spend(self):
        prose = ("\"Two gold for the bed,\" the innkeeper says. You pay for the bed and climb the stairs.")
        result = {"narration": prose, "player": {"gold_delta": 30}}
        _settle_stated_gold(result, "I pay for a bed and go up.")
        self.assertEqual(result["player"].get("gold_delta"), -2)

    def test_looking_at_goods_for_sale_costs_nothing(self):
        prose = "The stall holds lanterns and coils of rope. You look them over and move on."
        result = {"narration": prose, "player": {}, "inventory_changes": [{"name": "Lantern", "quantity_band": "small"}]}
        self.assertIsNone(_settle_stated_gold(result, "I look over what the stall has for sale."))
        self.assertNotIn("gold_band", result["player"])


class ALossIsTheItems(unittest.TestCase):
    """8B run 147, T30: "casting long shadows across the broken beams" took the lantern out of the pack."""

    def test_a_loss_word_elsewhere_in_the_sentence_is_no_loss(self):
        from app.world import _loss_shown

        prose = ("You step inside, lantern light cutting through the murky air. Your lantern flickers, casting long shadows "
                 "across the broken beams and scattered debris.")
        self.assertFalse(_loss_shown("Lantern", prose + "\nI go into the wreck's interior with the lantern lit."))

    def test_a_loss_of_the_item_still_counts(self):
        from app.world import _loss_shown

        self.assertTrue(_loss_shown("Lantern", "The lantern slips from your grip and shatters on the planks."))
        self.assertTrue(_loss_shown("Lantern", "You hand the lantern over to Wulfstan."))
        self.assertTrue(_loss_shown("Lantern", "You drop the lantern into the water."))


class CoinPutAwayIsCoinAlreadyCounted(unittest.TestCase):
    def test_the_sum_alone_is_read(self):
        # 8B run 147, T83: "I pocket the fifteen" the turn after the pay paid it again.
        self.assertEqual(prose_state.player_puts_away_coin("I pocket the fifteen and turn to Gunilda."), 15)
        self.assertEqual(prose_state.player_puts_away_coin("I pocket the two gold and nod."), 2)
        self.assertEqual(prose_state.player_puts_away_coin("I pocket the coins."), 0)
        self.assertIsNone(prose_state.player_puts_away_coin("I pocket the fifteen gold from the till."))
        self.assertIsNone(prose_state.player_puts_away_coin("I walk down to the dock."))


class AFixtureUsedIsNoThingTaken(unittest.TestCase):
    def test_a_bed_a_room_and_a_meal_are_not_taken_things(self):
        # 8B run 147, T64: "I take the bed Abel showed me" put "bed x1" in the pack.
        from app.world import _NOT_A_TAKEN_THING

        for word in ("bed", "room", "meal", "chair", "ferry"):
            self.assertIn(word, _NOT_A_TAKEN_THING, word)


class AConjunctionIsNoName(unittest.TestCase):
    def test_and_veyra_is_not_a_new_person(self):
        prose = "Rolf is watching, his grip tight on his pack. And Veyra, the spymaster, is watching you just as closely."
        self.assertEqual(_introduced_people(prose, ["Veyra Drowned", "Rolf Joliffe"], set()), [])

    def test_a_real_introduction_still_counts(self):
        prose = "Gareth Radley, the dockhand, leans against a stack of barrels."
        self.assertEqual([p["name"] for p in _introduced_people(prose, [], set())], ["Gareth Radley"])


class APlaceOnlyPointedAtIsNotReached(unittest.TestCase):
    LOW = ("you step between the pilings. you move deeper into the wharf until you reach a narrow passage "
           "that leads to the edge of the flats [[l8]].")

    def test_where_a_passage_leads_is_pointed_at(self):
        self.assertTrue(_place_only_pointed_at(self.LOW, "edge of the flats"))
        self.assertTrue(_place_only_pointed_at(self.LOW, "[[l8]]"))

    def test_a_place_come_out_onto_is_reached(self):
        self.assertFalse(_place_only_pointed_at("you come out onto the edge of the flats [[l8]], mud to the horizon.", "edge of the flats"))

    def test_pointed_at_then_reached_is_reached(self):
        low = "the path leads to the edge of the flats. you walk it and stand on the edge of the flats at last."
        self.assertFalse(_place_only_pointed_at(low, "edge of the flats"))


class ANameAskedAfterIsNoOpponent(unittest.TestCase):
    def test_asking_where_someone_is_does_not_roll_against_them(self):
        ctx = {
            "npcs": [{"code": "J", "name": "Elara Veyne"}, {"code": "R", "name": "Gareth Radley"}],
            "conversation_turn": {"present": ["R"], "addressed": ["J"]},
        }
        check = infer_check_from_action("I turn back into the Old Wharf and ask the nearest dockhand where Elara Veyne can be found.", ctx)
        self.assertIsNotNone(check)
        self.assertNotEqual(((check or {}).get("opposition") or {}).get("name"), "Elara Veyne")

    def test_a_leave_taking_then_a_walk_to_someone_else_is_no_roll_against_the_first(self):
        # 8B run 147, T54: "thank Mira, and go out to find Eda Jessop ... to ask" rolled against Mira.
        ctx = {
            "npcs": [{"code": "A", "name": "Mira Venn"}, {"code": "E", "name": "Eda Jessop"}],
            "locations": [{"code": "L3", "name": "The Harbour", "npcs": [{"code": "E", "name": "Eda Jessop"}]}],
            "conversation_turn": {"present": ["A"], "addressed": ["A"]},
        }
        line = ("I fold the sketch into my tunic, thank Mira, and go out to find Eda Jessop at her fish stall to ask "
                "whether a split-hulled boat was ever brought in.")
        check = infer_check_from_action(line, ctx)
        self.assertNotEqual(((check or {}).get("opposition") or {}).get("name"), "Mira Venn")
        # Thanked and then asked, she is still the other side.
        check = infer_check_from_action("I thank Mira for the receipt and ask her what the guild pays for rope.", ctx)
        self.assertEqual(((check or {}).get("opposition") or {}).get("name"), "Mira Venn")

    def test_the_debtor_named_in_a_question_to_someone_else_is_no_opponent(self):
        # 8B run 147, T89-T90: "ask Mira whether ... collected from Dunmore" and "a bonus for Dunmore" rolled against Dunmore.
        ctx = {
            "npcs": [{"code": "A", "name": "Mira Venn"}, {"code": "D", "name": "Gregory Dunmore"}],
            "conversation_turn": {"present": ["A", "D"], "addressed": ["A"]},
        }
        for line in (
            "I go back inside and ask Mira whether the guild wants that bread debt collected from Dunmore, and what it pays.",
            "\"A silver a coin and a bonus for Dunmore. I'll collect the bread debt.\" I ask Mira where Dunmore is to be found.",
        ):
            check = infer_check_from_action(line, ctx)
            self.assertEqual(((check or {}).get("opposition") or {}).get("name"), "Mira Venn", line)

    def test_asking_someone_present_still_rolls_against_them(self):
        ctx = {
            "npcs": [{"code": "J", "name": "Elara Veyne"}, {"code": "R", "name": "Gareth Radley"}],
            "conversation_turn": {"present": ["J", "R"], "addressed": ["J"]},
        }
        check = infer_check_from_action("I ask Elara Veyne what the journal says.", ctx)
        self.assertEqual(((check or {}).get("opposition") or {}).get("name"), "Elara Veyne")


if __name__ == "__main__":
    unittest.main()
