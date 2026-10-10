"""Tests for app/trade.py, the price ledger, settlement prices, offers and haggling (TODO n15, built but not wired).

Pure rules first (keys, categories, reference prices, haggling, alternatives, typed answers, fulfilment),
then the ledger and offer writers against a temporary database, then the leaf and no-foreign-writes checks
that keep the module unwired.

Run:  python -m unittest tests.test_trade
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-trade-test-"))
_ENV = {
    "AI_RPG_DB": str(_TMP / "world.db"),
    "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
    "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
    "AI_RPG_CONSOLIDATED_FACTS": str(_TMP / "facts.jsonl"),
    "AI_RPG_CAMPAIGN_SLOTS": str(_TMP / "slots"),
    "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
    "AI_RPG_PACK_DIR": str(_TMP / "packs"),
    "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
    "AI_RPG_IDEA_BANK": str(_TMP / "idea_bank"),
    "AI_RPG_LAUNCHER_PREFS": str(_TMP / "launcher_prefs.json"),
}
os.environ.update(_ENV)

from app import currency  # noqa: E402
from app import economy  # noqa: E402
from app import trade  # noqa: E402
from app import world  # noqa: E402
from app.db import connect, db_path, init_db  # noqa: E402
from app.relationships import get_relationship_summary  # noqa: E402
from app.rng import campaign_seed, rng_for  # noqa: E402
from app.skill_checks import OUTCOME_RANK  # noqa: E402

CSET = currency.theme_set("coin_medieval")
SEED = 1


def setUpModule():
    os.environ.update(_ENV)
    init_db()
    with connect() as conn:
        trade.ensure_schema(conn)


def _fresh_db() -> None:
    path = db_path()
    if path.exists():
        path.unlink()
    init_db()
    with connect() as conn:
        trade.ensure_schema(conn)
        economy.ensure_schema(conn)  # the sibling tables exist from the start so the table set is stable
        conn.execute(
            "INSERT OR IGNORE INTO player (id, name, health, max_health, level, xp, gold, current_location_id) "
            "VALUES (1, 'T', 20, 20, 1, 0, 12, NULL)"
        )
    conn.close()


def _table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    names = [
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")
    ]
    return {name: int(conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]) for name in names}


def _setting_keys(conn: sqlite3.Connection) -> set[str]:
    return {row["key"] for row in conn.execute("SELECT key FROM settings")}


def _make_keeper(conn: sqlite3.Connection, *, name: str = "Mara", attitude: str = "neutral",
                 personality: str = "", trust: int = 0, rank: str = "F") -> tuple[int, int]:
    """A locations row and an npcs row standing in it; returns (location_id, npc_id)."""
    cur = conn.execute(
        "INSERT INTO locations (code, name, kind, settlement_size) VALUES (?, ?, 'bakery', 'town')",
        (f"L{name}", f"{name}'s bakery"),
    )
    location_id = int(cur.lastrowid)
    cur = conn.execute(
        "INSERT INTO npcs (code, location_id, name, role, attitude, personality, trust, rank, stat_profile) "
        "VALUES (?, ?, ?, 'baker', ?, ?, ?, ?, '{\"charisma\": 12}')",
        (f"N{name}", location_id, name, attitude, personality, trust, rank),
    )
    return location_id, int(cur.lastrowid)


def _offer(**overrides) -> dict:
    base = dict(kind="buy", item_name="bread", quantity=1, unit_price=1000, cset=CSET, seller_npc_id=0,
                location_id=0, settlement_id="S3", turn=5)
    base.update(overrides)
    return trade.make_offer(**base)


_OFFER_SHAPE = {
    "id": int, "code": str, "status": str, "kind": str, "item_key": str, "item_name": str, "category": str,
    "quantity": int, "unit_price": int, "total_price": int, "asking_price": int, "currency_set": str,
    "seller_npc_id": int, "location_id": int, "settlement_id": str, "offered_turn": int, "answered_turn": int,
    "expires_turn": int, "rounds": int, "max_rounds": int, "last_player_bid": int, "counter_price": int,
    "goods_given": list, "terms_id": int, "note": str, "price_basis": str,
}
_HAGGLE_SHAPE = {
    "decision": str, "price": int, "floor": int, "ceiling_pct": float, "mood": str, "band": str, "outcome": str,
    "round": int, "rounds_left": int, "line": str,
}
_MULTIPLIER_SHAPE = {
    "settlement_id": str, "category": str, "day": int, "mult": float, "supply": float, "demand": float,
    "season": str, "season_mult": float, "scarcity_mult": float, "drift_mult": float, "flavour_mult": float,
    "events": list, "reason": str,
}


def _assert_shape(test: unittest.TestCase, value: dict, shape: dict[str, type]) -> None:
    test.assertEqual(set(value), set(shape), f"keys differ: {sorted(set(value) ^ set(shape))}")
    for key, kind in shape.items():
        test.assertIsInstance(value[key], kind, f"{key} should be {kind.__name__}, got {value[key]!r}")
        if kind is int:
            test.assertNotIsInstance(value[key], bool, key)


def _assert_offer(test: unittest.TestCase, offer: dict) -> None:
    _assert_shape(test, offer, _OFFER_SHAPE)
    test.assertIn(offer["status"], trade.OFFER_STATES)
    test.assertIn(offer["kind"], trade.OFFER_KINDS)
    test.assertIn(offer["price_basis"], ("prose", "ledger_first", "ledger_avg", "reference", "counter", ""))
    for goods in offer["goods_given"]:
        test.assertEqual(set(goods), {"item_key", "item_name", "quantity"})


def _assert_haggle(test: unittest.TestCase, result: dict) -> None:
    keys = set(_HAGGLE_SHAPE) | {"relationship_event"}
    test.assertEqual(set(result), keys)
    for key, kind in _HAGGLE_SHAPE.items():
        test.assertIsInstance(result[key], kind, key)
    test.assertIn(result["decision"], ("accept", "counter", "refuse", "insulted"))
    test.assertIn(result["mood"], trade.MOODS)
    test.assertIn(result["band"], trade.BAND_CEILING)
    test.assertTrue(result["outcome"] in OUTCOME_RANK or result["outcome"] == "not_rolled", result["outcome"])
    test.assertIn(result["relationship_event"], ("traded_npc", "lied_to_npc_caught", None))
    test.assertLessEqual(len(result["line"]), 160)


def _assert_inventory_change(test: unittest.TestCase, change: dict) -> None:
    test.assertIsInstance(change["name"], str)
    test.assertTrue(change["name"])
    test.assertIsInstance(change["quantity_delta"], int)
    test.assertEqual(change["source"], "trade")
    test.assertLessEqual(set(change), {"name", "quantity_delta", "item_type", "description", "source", "reason"})


def _assert_journal_note(test: unittest.TestCase, note: dict) -> None:
    test.assertEqual(set(note), {"kind", "content"})
    test.assertEqual(note["kind"], "trade")
    test.assertLessEqual(len(note["kind"]), 40)
    test.assertLessEqual(len(note["content"]), 900)


# ---------------------------------------------------------------------------
# Pure: keys, categories, reference prices
# ---------------------------------------------------------------------------


class ItemKeyTests(unittest.TestCase):
    def test_item_key_normalisation_and_aliases(self):
        self.assertEqual(trade.item_key("a loaf of bread"), "bread")
        self.assertEqual(trade.item_key("Room for the night"), "lodging:night")
        self.assertEqual(trade.item_key("[tagged] Rope"), "rope")
        self.assertEqual(trade.item_key("The night's lodging"), "lodging:night")
        self.assertEqual(trade.item_key("a bed for the night"), "lodging:night")
        self.assertEqual(trade.item_key("The Baker's loaf"), "bread")
        self.assertEqual(trade.item_key("bowl of stew"), "meal")
        self.assertEqual(trade.item_key("a tankard of ale"), "ale")
        self.assertEqual(trade.item_key("healing draught"), "healing_potion")
        self.assertEqual(trade.item_key("trail rations"), "ration")
        self.assertEqual(trade.item_key("ferry"), "passage")
        self.assertEqual(trade.item_key("  Iron   Sword "), "iron sword")
        self.assertEqual(trade.item_key("x" * 90), "x" * 60)
        self.assertEqual(trade.item_key(""), "")

    def test_every_alias_key_has_a_category_and_the_categories_are_goods(self):
        for _, key in trade.ITEM_ALIASES:
            self.assertIn(key, trade.KEY_CATEGORIES)
        for key, cat in trade.KEY_CATEGORIES.items():
            self.assertIn(cat, economy.GOODS_CATEGORIES, key)
        for cat in trade.CATEGORY_KEYWORDS:
            self.assertIn(cat, economy.GOODS_CATEGORIES)
        self.assertNotIn("misc", trade.CATEGORY_KEYWORDS)

    def test_categorize_by_type_then_keywords(self):
        self.assertEqual(trade.categorize("knife", "weapon"), "weapons")
        self.assertEqual(trade.categorize("knife"), "tools")
        self.assertEqual(trade.categorize("leather boots"), "cloth")
        self.assertEqual(trade.categorize("iron sword"), "weapons")
        self.assertEqual(trade.categorize("lamp oil"), "fuel")
        self.assertEqual(trade.categorize("fuel cell"), "transport")
        self.assertEqual(trade.categorize("spell scroll"), "magic")
        self.assertEqual(trade.categorize("odd gizmo"), "misc")
        self.assertEqual(trade.categorize("dried apple", "consumable"), "food")
        self.assertEqual(trade.categorize("cider", "consumable"), "drink")
        self.assertEqual(trade.categorize("mystery jar", "consumable"), "food")
        self.assertEqual(trade.categorize("thick cloak", "clothing"), "cloth")
        self.assertEqual(trade.categorize("water skin"), "tools")  # alias key wins over the "water" keyword

    def test_reference_price_key_then_category_then_none(self):
        self.assertEqual(trade.reference_price("a loaf of bread", CSET), currency.from_legacy_gold(0.5, CSET))
        self.assertEqual(trade.reference_price("healing potion", CSET), currency.from_legacy_gold(12, CSET))
        self.assertEqual(trade.reference_price("iron sword", CSET), currency.from_legacy_gold(15, CSET))
        self.assertEqual(trade.reference_price("odd gizmo", CSET), currency.from_legacy_gold(2, CSET))
        self.assertEqual(trade.reference_price("odd gizmo", CSET, category="luxury"), currency.from_legacy_gold(40, CSET))
        self.assertIsNone(trade.reference_price("odd gizmo", CSET, category="relic"))
        credits = currency.theme_set("credits")
        self.assertEqual(trade.reference_price("bread", credits), 5)

    def test_reference_table_matches_the_design_numbers(self):
        self.assertEqual(trade.REFERENCE_GOLD["items"], {
            "bread": 0.5, "cheese": 1.0, "meal": 1.5, "ale": 0.5, "wine": 2.0, "ration": 1.0, "waterskin": 2.0,
            "rope": 1.5, "torch": 0.5, "arrow": 0.2, "bandage": 1.0, "healing_potion": 12.0,
            "lodging:night": 2.0, "passage": 3.0,
        })
        self.assertEqual(trade.REFERENCE_GOLD["categories"], {
            "food": 1.0, "drink": 1.0, "lodging": 2.0, "cloth": 4.0, "tools": 2.0, "weapons": 15.0, "armor": 25.0,
            "medicine": 6.0, "materials": 2.0, "luxury": 40.0, "transport": 30.0, "fuel": 1.0, "services": 3.0,
            "knowledge": 8.0, "magic": 60.0, "misc": 2.0,
        })
        self.assertEqual(set(trade.REFERENCE_GOLD["categories"]), set(economy.GOODS_CATEGORIES))
        self.assertEqual((trade.OFFER_TTL_TURNS, trade.MAX_OPEN_OFFERS, trade.MAX_ROUNDS, trade.TRUSTED_MAX_ROUNDS),
                         (3, 4, 2, 3))
        self.assertEqual((trade.LOWBALL_FRACTION, trade.INSULT_RAISE, trade.COUNTER_STEP_MIN), (0.5, 0.10, 1))
        self.assertEqual(trade.BAND_CEILING, {"Hostile": 0.0, "Unfriendly": 0.03, "Neutral": 0.10,
                                              "Friendly": 0.15, "Trusted": 0.20, "Devoted": 0.25})


# ---------------------------------------------------------------------------
# Pure: turn prices and offers
# ---------------------------------------------------------------------------


class TurnPriceTests(unittest.TestCase):
    def test_prices_from_turn_pairs_one_item_one_price(self):
        result = {"inventory_changes": [{"name": "bread", "quantity_delta": 2}, {"name": "old boots", "quantity_delta": -1}]}
        found = trade.prices_from_turn(
            result, narration='"Ten silver for two loaves," she says. You hand over 10 silver.',
            gold_note={"source": "prose_paid", "gold_delta": -1}, cset=CSET,
        )
        self.assertEqual(found, [{"item_name": "bread", "unit_price": 500, "quantity": 2, "source": "prose_paid"}])

    def test_prices_from_turn_falls_back_to_gold_note(self):
        result = {"inventory_changes": [{"name": "rope", "quantity_delta": 1}]}
        found = trade.prices_from_turn(result, narration="She hands you the rope.",
                                       gold_note={"source": "stated", "gold_delta": -2}, cset=CSET)
        self.assertEqual(found, [{"item_name": "rope", "unit_price": 20000, "quantity": 1, "source": "stated"}])
        found = trade.prices_from_turn(result, narration="You pay 3 silver for it.", gold_note={"source": "odd"}, cset=CSET)
        self.assertEqual(found[0]["source"], "prose")

    def test_prices_from_turn_ambiguous_returns_empty(self):
        two_items = {"inventory_changes": [{"name": "bread", "quantity_delta": 1}, {"name": "cheese", "quantity_delta": 1}]}
        self.assertEqual(trade.prices_from_turn(two_items, narration="You pay 5 silver.", gold_note=None, cset=CSET), [])
        one_item = {"inventory_changes": [{"name": "bread", "quantity_delta": 1}]}
        self.assertEqual(trade.prices_from_turn(one_item, narration="Five silver, or six silver for the big one.",
                                                gold_note=None, cset=CSET), [])
        self.assertEqual(trade.prices_from_turn(one_item, narration="She wraps the loaf.", gold_note=None, cset=CSET), [])
        self.assertEqual(trade.prices_from_turn({}, narration="You pay 5 silver.", gold_note=None, cset=CSET), [])
        negated = trade.prices_from_turn(one_item, narration="You do not pay 5 silver. It costs 2 silver.",
                                         gold_note=None, cset=CSET)
        self.assertEqual(negated[0]["unit_price"], 200)


class MakeOfferTests(unittest.TestCase):
    def test_make_offer_validates_kind_quantity_price(self):
        with self.assertRaises(ValueError):
            _offer(kind="steal")
        with self.assertRaises(ValueError):
            _offer(quantity=0)
        with self.assertRaises(ValueError):
            _offer(unit_price=-1)
        with self.assertRaises(ValueError):
            _offer(item_name="   ")
        offer = _offer(quantity=2, unit_price=500, goods_given=[{"item_name": "ore", "quantity": 3}])
        _assert_offer(self, offer)
        self.assertEqual((offer["id"], offer["code"], offer["status"]), (0, "", "offered"))
        self.assertEqual((offer["total_price"], offer["asking_price"]), (1000, 1000))
        self.assertEqual(offer["expires_turn"], 5 + trade.OFFER_TTL_TURNS)
        self.assertEqual(offer["max_rounds"], trade.MAX_ROUNDS)
        self.assertEqual(offer["category"], "food")
        self.assertEqual(offer["currency_set"], "coin_medieval")
        self.assertEqual(offer["goods_given"], [{"item_key": "ore", "item_name": "ore", "quantity": 3}])
        self.assertEqual(_offer(max_rounds=5)["max_rounds"], 5)
        self.assertEqual(_offer(unit_price=0)["asking_price"], 0)


# ---------------------------------------------------------------------------
# Pure: haggling
# ---------------------------------------------------------------------------


class HaggleTests(unittest.TestCase):
    FRIENDLY = {"affinity": 40, "affinity_band": "Friendly"}

    def test_keeper_mood_table(self):
        self.assertEqual(trade.keeper_mood(None), "neutral")
        self.assertEqual(trade.keeper_mood({"attitude": "hostile", "personality": "", "trust": 0}), "hostile")
        self.assertEqual(trade.keeper_mood({"attitude": "furious", "personality": "warm", "trust": 0}), "hostile")
        for word in ("dismissive", "apprehensive", "condescending", "cold", "wary", "suspicious", "sullen", "guarded"):
            self.assertEqual(trade.keeper_mood({"attitude": word, "personality": "", "trust": 0}), "cold", word)
        for word in ("cold", "stoic", "secretive", "greedy", "miserly", "grasping"):
            self.assertEqual(trade.keeper_mood({"attitude": "neutral", "personality": f"a {word} sort", "trust": 0}), "cold", word)
        for word in ("warm", "cordial", "friendly", "cheerful", "kind", "welcoming", "grateful"):
            self.assertEqual(trade.keeper_mood({"attitude": word, "personality": "", "trust": 0}), "warm", word)
        for word in ("warm", "kind", "open", "generous", "cheerful"):
            self.assertEqual(trade.keeper_mood({"attitude": "neutral", "personality": word, "trust": 0}), "warm", word)
        self.assertEqual(trade.keeper_mood({"attitude": "neutral", "personality": "", "trust": 0}), "neutral")
        # trust moves one step: hostile -> cold -> neutral -> warm and back
        self.assertEqual(trade.keeper_mood({"attitude": "hostile", "personality": "", "trust": 40}), "cold")
        self.assertEqual(trade.keeper_mood({"attitude": "neutral", "personality": "", "trust": 40}), "warm")
        self.assertEqual(trade.keeper_mood({"attitude": "warm", "personality": "", "trust": 99}), "warm")
        self.assertEqual(trade.keeper_mood({"attitude": "warm", "personality": "", "trust": -20}), "neutral")
        self.assertEqual(trade.keeper_mood({"attitude": "hostile", "personality": "", "trust": -50}), "hostile")
        self.assertEqual(trade.keeper_mood({"attitude": "neutral", "personality": "", "trust": 39}), "neutral")

    def test_discount_ceiling_by_band_mood_and_market(self):
        for band, expected in trade.BAND_CEILING.items():
            self.assertAlmostEqual(trade.discount_ceiling(band=band, mood="neutral"), expected, places=4, msg=band)
        self.assertEqual(trade.discount_ceiling(band="Friendly", mood="hostile"), 0.0)
        self.assertEqual(trade.discount_ceiling(band="Hostile", mood="warm"), 0.0)
        self.assertAlmostEqual(trade.discount_ceiling(band="Friendly", mood="cold"), 0.10, places=4)
        self.assertAlmostEqual(trade.discount_ceiling(band="Friendly", mood="warm"), 0.20, places=4)
        self.assertAlmostEqual(trade.discount_ceiling(band="Devoted", mood="warm"), 0.30, places=4)  # clamp
        self.assertAlmostEqual(trade.discount_ceiling(band="Unfriendly", mood="cold"), 0.0, places=4)
        scarce = {"reason": "ok", "mult": 1.5}
        glut = {"reason": "ok", "mult": 0.7}
        self.assertAlmostEqual(trade.discount_ceiling(band="Friendly", mood="neutral", multiplier=scarce), 0.075, places=4)
        self.assertAlmostEqual(trade.discount_ceiling(band="Friendly", mood="neutral", multiplier=glut), 0.20, places=4)
        unknown = {"reason": "unknown_settlement", "mult": 0.2}
        self.assertAlmostEqual(trade.discount_ceiling(band="Friendly", mood="neutral", multiplier=unknown), 0.15, places=4)
        self.assertAlmostEqual(trade.discount_ceiling(band="Nonsense", mood="neutral"), 0.10, places=4)

    def test_haggle_check_inputs(self):
        offer = _offer()
        keeper = {"name": "Mara", "rank": "C", "attitude": "wary", "stat_profile": '{"charisma": 14}'}
        inputs = trade.haggle_check_inputs(offer, keeper, player_line="Let me haggle", cset=CSET)
        self.assertEqual(inputs["skill_code"], "persuasion")
        self.assertEqual(inputs["opposition"], {"name": "Mara", "rank": "C", "attitude": "wary", "stats": {"charisma": 14}})
        self.assertEqual(inputs["context_note"], "haggling over bread at 10 silver")
        self.assertEqual(inputs["weapon_or_tool"], "")
        self.assertEqual(trade.haggle_check_inputs(offer, None, player_line="What is it worth?", cset=CSET)["skill_code"], "appraise")
        self.assertEqual(trade.haggle_check_inputs(offer, None, cset=CSET)["opposition"]["name"], "the seller")
        self.assertEqual(trade.haggle_check_inputs(offer, {"stat_profile": "not json"}, cset=CSET)["opposition"]["stats"], {})

    def test_resolve_haggle_hostile_refuses_without_roll(self):
        offer = _offer()
        by_band = trade.resolve_haggle(offer, bid=860, check={"outcome": "success", "margin": 5},
                                       relationship={"affinity": -80, "affinity_band": "Hostile"}, keeper_row=None, cset=CSET)
        _assert_haggle(self, by_band)
        self.assertEqual((by_band["decision"], by_band["outcome"], by_band["price"]), ("refuse", "not_rolled", 1000))
        self.assertEqual(by_band["ceiling_pct"], 0.0)
        self.assertIsNone(by_band["relationship_event"])
        by_mood = trade.resolve_haggle(offer, bid=860, check={"outcome": "success"}, relationship=self.FRIENDLY,
                                       keeper_row={"attitude": "hostile", "personality": "", "trust": 0}, cset=CSET)
        self.assertEqual((by_mood["decision"], by_mood["outcome"], by_mood["mood"]), ("refuse", "not_rolled", "hostile"))
        with self.assertRaises(ValueError):
            trade.resolve_haggle(offer, bid=0, check={"outcome": "success"}, relationship=None, keeper_row=None, cset=CSET)

    def test_resolve_haggle_lowball_is_insult(self):
        offer = _offer()
        low = trade.resolve_haggle(offer, bid=400, check={"outcome": "critical_success"}, relationship=self.FRIENDLY,
                                   keeper_row=None, cset=CSET)
        _assert_haggle(self, low)
        self.assertEqual(low["decision"], "insulted")
        self.assertEqual(low["price"], 1100)
        self.assertEqual(low["rounds_left"], 0)
        self.assertEqual(low["relationship_event"], "lied_to_npc_caught")
        devoted = trade.resolve_haggle(offer, bid=400, check={"outcome": "success"},
                                       relationship={"affinity": 95, "affinity_band": "Devoted"}, keeper_row=None, cset=CSET)
        self.assertNotEqual(devoted["decision"], "insulted")
        self.assertEqual(devoted["decision"], "counter")
        self.assertEqual(devoted["price"], 750)  # the Devoted floor

    def test_resolve_haggle_outcomes(self):
        offer = _offer()
        expected = {
            "critical_failure": ("insulted", 1100, 0, None),
            "failure": ("counter", 1000, 1, None),
            "partial": ("counter", 930, 1, None),
            "success": ("accept", 860, 1, "traded_npc"),
            "critical_success": ("accept", 860, 1, "traded_npc"),
        }
        for outcome, (decision, price, left, event) in expected.items():
            with self.subTest(outcome=outcome):
                result = trade.resolve_haggle(offer, bid=860, check={"outcome": outcome, "margin": 1},
                                              relationship=self.FRIENDLY, keeper_row=None, cset=CSET)
                _assert_haggle(self, result)
                self.assertEqual(result["decision"], decision)
                self.assertEqual(result["price"], price)
                self.assertEqual(result["floor"], 850)
                self.assertAlmostEqual(result["ceiling_pct"], 0.15)
                self.assertEqual((result["mood"], result["band"], result["outcome"]), ("neutral", "Friendly", outcome))
                self.assertEqual((result["round"], result["rounds_left"]), (1, left))
                self.assertEqual(result["relationship_event"], event)
        # success below the floor counters at the floor; a critical success reaches a little under it
        under = trade.resolve_haggle(offer, bid=800, check={"outcome": "success"}, relationship=self.FRIENDLY,
                                     keeper_row=None, cset=CSET)
        self.assertEqual((under["decision"], under["price"]), ("counter", 850))
        crit = trade.resolve_haggle(offer, bid=810, check={"outcome": "critical_success"}, relationship=self.FRIENDLY,
                                    keeper_row=None, cset=CSET)
        self.assertEqual((crit["decision"], crit["price"]), ("accept", 810))
        crit_low = trade.resolve_haggle(offer, bid=600, check={"outcome": "critical_success"}, relationship=self.FRIENDLY,
                                        keeper_row=None, cset=CSET)
        self.assertEqual((crit_low["decision"], crit_low["price"]), ("counter", 808))
        # a bid at the price on the table is simply taken, no roll needed
        full = trade.resolve_haggle(offer, bid=1000, check={"outcome": "failure"}, relationship=None, keeper_row=None, cset=CSET)
        self.assertEqual((full["decision"], full["price"], full["outcome"]), ("accept", 1000, "not_rolled"))
        # the same without a check at all, and for a free offer the bid is taken at the table price of 0
        self.assertEqual(trade.resolve_haggle(offer, bid=1000, check=None, relationship=None, keeper_row=None, cset=CSET)["decision"], "accept")
        free = trade.resolve_haggle(_offer(unit_price=0), bid=100, check={"outcome": "partial"}, relationship=None,
                                    keeper_row=None, cset=CSET)
        self.assertEqual((free["decision"], free["price"], free["outcome"]), ("accept", 0, "not_rolled"))
        # an outcome the table does not know (dice off) is read as partial
        odd = trade.resolve_haggle(offer, bid=860, check={"outcome": "narrative"}, relationship=None, keeper_row=None, cset=CSET)
        self.assertEqual(odd["outcome"], "partial")

    def test_resolve_haggle_rounds_left_and_relationship_event(self):
        last_round = _offer()
        last_round["rounds"] = 1
        failed = trade.resolve_haggle(last_round, bid=900, check={"outcome": "failure"}, relationship=self.FRIENDLY,
                                      keeper_row=None, cset=CSET)
        self.assertEqual((failed["decision"], failed["round"], failed["rounds_left"], failed["price"]), ("refuse", 2, 0, 1000))
        trusted = trade.resolve_haggle(last_round, bid=900, check={"outcome": "failure"},
                                       relationship={"affinity": 70, "affinity_band": "Trusted"}, keeper_row=None, cset=CSET)
        self.assertEqual((trusted["decision"], trusted["rounds_left"]), ("counter", 1))  # Trusted gets three rounds
        countered = _offer()
        countered.update({"status": "countered", "counter_price": 950, "total_price": 950, "rounds": 1})
        taken = trade.resolve_haggle(countered, bid=950, check={"outcome": "failure"}, relationship=None, keeper_row=None, cset=CSET)
        self.assertEqual((taken["decision"], taken["price"], taken["relationship_event"]), ("accept", 950, "traded_npc"))
        # the market changes the ceiling: scarce halves it, so the same bid now draws a counter
        scarce = {"reason": "ok", "mult": 1.6}
        tight = trade.resolve_haggle(_offer(), bid=860, check={"outcome": "success"}, relationship=self.FRIENDLY,
                                     keeper_row=None, cset=CSET, multiplier=scarce)
        self.assertEqual((tight["decision"], tight["floor"]), ("counter", 925))
        # the relationship band can be given as a number alone
        by_number = trade.resolve_haggle(_offer(), bid=860, check={"outcome": "success"}, relationship={"affinity": 40},
                                         keeper_row=None, cset=CSET)
        self.assertEqual(by_number["band"], "Friendly")


# ---------------------------------------------------------------------------
# Pure: alternatives, typed answers, fulfilment
# ---------------------------------------------------------------------------


class AlternativesTests(unittest.TestCase):
    def test_alternatives_cheaper_better_other(self):
        offer = _offer(item_name="cheese", unit_price=10000, category="food")
        rows = [
            {"item_key": "bread", "item_name": "bread", "category": "food", "avg_price": 5000.0},
            {"item_key": "honey cake", "item_name": "honey cake", "category": "food", "avg_price": 14000.0},
            {"item_key": "cheese", "item_name": "cheese", "category": "food", "avg_price": 10000.0},
            {"item_key": "rope", "item_name": "rope", "category": "tools", "avg_price": 100.0},
        ]
        out = trade.alternatives(offer, index_rows=rows, venue_kind="inn", cset=CSET)
        self.assertEqual([a["kind"] for a in out], ["cheaper", "better", "other"])
        self.assertEqual(out[0]["item_key"], "bread")
        self.assertEqual(out[0]["unit_price"], 5000)
        self.assertEqual(out[1]["item_key"], "honey cake")  # the nearest dearer item, before the 15000 reference meal
        self.assertEqual(out[1]["unit_price"], 14000)
        self.assertEqual(out[2]["category"], "lodging")
        self.assertEqual(out[2]["unit_price"], currency.from_legacy_gold(2, CSET))
        for entry in out:
            self.assertEqual(set(entry), {"kind", "item_name", "item_key", "category", "unit_price", "display", "reason"})
            self.assertIsInstance(entry["unit_price"], int)
        self.assertLessEqual(len(out), trade.MAX_ALTERNATIVES)
        # the market moves every suggested price; at 1.2 bread is still under 0.8 of the asking unit
        dear = trade.alternatives(offer, index_rows=rows, venue_kind="inn", cset=CSET, multiplier={"reason": "ok", "mult": 1.2})
        self.assertEqual((dear[0]["kind"], dear[0]["unit_price"]), ("cheaper", 6000))
        # at 2.0 nothing of the same category is cheaper any more, so the first suggestion is a dearer item
        doubled = trade.alternatives(offer, index_rows=rows, venue_kind="inn", cset=CSET, multiplier={"reason": "ok", "mult": 2.0})
        self.assertEqual(doubled[0]["kind"], "better")
        # reference items of the same category stand in when the ledger is empty
        empty = trade.alternatives(_offer(item_name="bread", unit_price=5000), index_rows=[], venue_kind="bakery", cset=CSET)
        self.assertEqual([a["kind"] for a in empty], ["better"])
        self.assertEqual(empty[0]["item_key"], "cheese")

    def test_alternatives_nothing_for_sale_kind(self):
        offer = _offer(item_name="odd gizmo", unit_price=500, category="misc")
        self.assertEqual(trade.alternatives(offer, index_rows=[], venue_kind="well", cset=CSET), [])
        self.assertEqual(trade.alternatives(offer, index_rows=[], venue_kind="guild hall", cset=CSET), [])
        self.assertEqual(trade.alternatives(offer, index_rows=[], venue_kind="", cset=CSET), [])

    def test_trade_reads_economy_venue_categories_and_keeps_no_copy(self):
        self.assertFalse(hasattr(trade, "VENUE_CATEGORIES"))
        source = (ROOT / "app" / "trade.py").read_text(encoding="utf-8")
        self.assertNotIn("VENUE_CATEGORIES =", source)
        self.assertIn("economy.VENUE_CATEGORIES", source)
        smithy = trade.alternatives(_offer(item_name="iron sword", unit_price=150000, category="weapons"),
                                    index_rows=[], venue_kind="smithy", cset=CSET)
        self.assertEqual(len(smithy), trade.MAX_ALTERNATIVES)
        self.assertEqual((smithy[0]["kind"], smithy[0]["item_key"]), ("cheaper", "arrow"))  # the reference arrow
        others = [a["category"] for a in smithy if a["kind"] == "other"]
        self.assertEqual(others, [c for c in economy.VENUE_CATEGORIES["smithy"] if c != "weapons"][:len(others)])
        self.assertEqual(others, ["tools", "materials"])


class AnswerFromLineTests(unittest.TestCase):
    def test_answer_from_line_accept_decline_haggle_and_one_offer_rule(self):
        bread = {**_offer(), "id": 3, "code": "T3"}
        cheese = {**_offer(item_name="cheese", unit_price=800), "id": 4, "code": "T4"}
        self.assertEqual(trade.answer_from_line([bread], "Deal.", cset=CSET), {"offer_id": 3, "action": "accept", "bid": None})
        self.assertEqual(trade.answer_from_line([bread], "I'll take it", cset=CSET)["action"], "accept")
        self.assertEqual(trade.answer_from_line([bread], "No deal, too much.", cset=CSET), {"offer_id": 3, "action": "decline", "bid": None})
        self.assertEqual(trade.answer_from_line([bread], "I'll pass.", cset=CSET)["action"], "decline")
        self.assertEqual(trade.answer_from_line([bread], "I'll give you 3 silver for it", cset=CSET),
                         {"offer_id": 3, "action": "haggle", "bid": 300})
        self.assertEqual(trade.answer_from_line([bread], "Here, 10 silver.", cset=CSET)["action"], "accept")
        self.assertEqual(trade.answer_from_line([bread], "I'll give you 12 silver", cset=CSET)["action"], "accept")
        self.assertIsNone(trade.answer_from_line([bread], "What a fine morning.", cset=CSET))
        self.assertIsNone(trade.answer_from_line([bread], "", cset=CSET))
        self.assertIsNone(trade.answer_from_line([], "deal", cset=CSET))
        # two open offers: the line must name one
        self.assertIsNone(trade.answer_from_line([bread, cheese], "deal", cset=CSET))
        self.assertEqual(trade.answer_from_line([bread, cheese], "I'll take the cheese, deal", cset=CSET)["offer_id"], 4)
        self.assertEqual(trade.answer_from_line([bread, cheese], "7 silver for the cheese", cset=CSET),
                         {"offer_id": 4, "action": "haggle", "bid": 700})
        # a negated clause is not an answer
        self.assertIsNone(trade.answer_from_line([bread], "I won't say deal", cset=CSET))
        # a bare accept word inside ordinary prose is not an answer either: not a question, and short or
        # naming the item or a coin
        self.assertIsNone(trade.answer_from_line([bread], "What have you done?", cset=CSET))
        self.assertIsNone(trade.answer_from_line([bread], "Are we done here, then?", cset=CSET))
        self.assertIsNone(trade.answer_from_line([bread], "he sold me out", cset=CSET))
        self.assertIsNone(trade.answer_from_line([bread], "When the baking is done I will come back for a word with you.", cset=CSET))
        self.assertEqual(trade.answer_from_line([bread], "Done, then.", cset=CSET)["action"], "accept")
        self.assertEqual(trade.answer_from_line([bread], "Agreed, the bread is worth every coin you ask of me today.", cset=CSET)["action"], "accept")
        self.assertEqual(trade.answer_from_line([bread], "Very well, it is a deal, the silver is yours once I have counted it.", cset=CSET)["action"], "accept")
        self.assertEqual(trade.answer_from_line([bread], "I'll pay, though it is dear and I would rather not have to.", cset=CSET)["action"], "accept")
        # a countered offer compares against the counter price
        countered = {**bread, "status": "countered", "counter_price": 900, "total_price": 900}
        self.assertEqual(trade.answer_from_line([countered], "9 silver then", cset=CSET)["action"], "accept")
        self.assertEqual(trade.answer_from_line([countered], "8 silver then", cset=CSET)["bid"], 800)


class FulfilmentTests(unittest.TestCase):
    def test_fulfilment_proposal_buy_sell_service(self):
        not_yet = trade.fulfilment_proposal(_offer(), cset=CSET)
        self.assertEqual(not_yet, {"error": "not_accepted", "status": "offered"})
        buy = {**_offer(quantity=2, unit_price=10000, seller_npc_id=7), "status": "accepted", "total_price": 20000}
        got = trade.fulfilment_proposal(buy, cset=CSET, seller_name="Mara")
        self.assertEqual(got["money_delta_units"], -20000)
        self.assertEqual(got["gold_delta_legacy"], -2)
        self.assertEqual(got["inventory_changes"], [{"name": "bread", "quantity_delta": 2, "item_type": "consumable",
                                                     "source": "trade", "reason": "offer_accepted"}])
        for change in got["inventory_changes"]:
            _assert_inventory_change(self, change)
        self.assertEqual((got["relationship_event"], got["npc_id"], got["agreement"]), ("traded_npc", 7, False))
        _assert_journal_note(self, got["journal"])
        self.assertEqual(got["journal"]["content"], "Bought 2 bread for 2 gold from Mara.")
        self.assertEqual(got["ledger"], {"item_name": "bread", "unit_price": 10000, "quantity": 2, "source": "offer_accepted"})
        sell = {**_offer(kind="sell", item_name="iron sword", unit_price=90000), "status": "accepted", "total_price": 90000}
        sold = trade.fulfilment_proposal(sell, cset=CSET)
        self.assertEqual((sold["money_delta_units"], sold["gold_delta_legacy"]), (90000, 9))
        self.assertEqual(sold["inventory_changes"][0]["quantity_delta"], -1)
        self.assertNotIn("item_type", sold["inventory_changes"][0])
        self.assertTrue(sold["journal"]["content"].startswith("Sold 1 iron sword for 9 gold to the seller."))
        service = {**_offer(kind="service", item_name="sharpening", unit_price=500,
                            goods_given=[{"item_name": "iron ore", "quantity": 3}]), "status": "accepted"}
        agreed = trade.fulfilment_proposal(service, cset=CSET)
        self.assertEqual((agreed["money_delta_units"], agreed["gold_delta_legacy"], agreed["agreement"]), (0, 0, True))
        self.assertEqual(agreed["inventory_changes"], [{"name": "iron ore", "quantity_delta": -3, "source": "trade", "reason": "hand_over"}])
        self.assertIsNone(agreed["ledger"])
        _assert_journal_note(self, agreed["journal"])
        # a night's lodging or a service is not a thing in the pack
        night = {**_offer(item_name="room for the night", unit_price=20000), "status": "accepted", "total_price": 20000}
        self.assertEqual(trade.fulfilment_proposal(night, cset=CSET)["inventory_changes"], [])
        ferry = {**_offer(item_name="ferry", unit_price=30000), "status": "accepted", "total_price": 30000}
        self.assertEqual(trade.fulfilment_proposal(ferry, cset=CSET)["inventory_changes"], [])


# ---------------------------------------------------------------------------
# Database: ledger, quotes, offers
# ---------------------------------------------------------------------------


class LedgerDbTests(unittest.TestCase):
    def setUp(self):
        _fresh_db()

    def test_schema_is_idempotent(self):
        with connect() as conn:
            trade.ensure_schema(conn)
            trade.ensure_schema(conn)
            names = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        for table in ("price_ledger", "price_index", "trade_offers"):
            self.assertIn(table, names)
            self.assertNotIn(table, world.WORLD_TABLES)
            self.assertNotIn(table, world.RESTORE_ORDER)
            self.assertNotIn(table, world.AUTOINC_TABLES)
            self.assertNotIn(table, world._REPLACE_ONLY_WHEN_EXPORTED)

    def test_record_price_first_kept_and_average_moves(self):
        with connect() as conn:
            first = trade.record_price(conn, item_name="a loaf of bread", unit_price=500, settlement_id="S1", turn=3,
                                       currency_set="coin_medieval")
            second = trade.record_price(conn, item_name="Bread", unit_price=700, settlement_id="S2", turn=4)
            known = trade.known_price(conn, "bread")
            rows = trade.ledger_for(conn, "bread")
            here = trade.ledger_for(conn, "bread", settlement_id="S1")
        self.assertEqual((first["first"], first["first_price"], first["avg_price"], first["sample_count"], first["outlier"]),
                         (True, 500, 500.0, 1, False))
        self.assertEqual((second["first"], second["first_price"], second["avg_price"], second["sample_count"], second["outlier"]),
                         (False, 500, 600.0, 2, False))
        self.assertEqual(first["item_key"], "bread")
        self.assertEqual((known["first_price"], known["avg_price"], known["sample_count"], known["min_price"],
                          known["max_price"], known["last_price"], known["last_turn"], known["category"]),
                         (500, 600.0, 2, 500, 700, 700, 4, "food"))
        self.assertEqual(known["item_name"], "a loaf of bread")
        self.assertEqual([r["unit_price"] for r in rows], [700, 500])  # newest first
        self.assertEqual([r["settlement_id"] for r in here], ["S1"])
        self.assertIsNone(trade.known_price(connect(), "nothing like it"))

    def test_record_price_outlier_recorded_not_averaged(self):
        with connect() as conn:
            for price in (500, 500, 500):
                trade.record_price(conn, item_name="bread", unit_price=price)
            spike = trade.record_price(conn, item_name="bread", unit_price=5000)
            known = trade.known_price(conn, "bread")
            rows = trade.ledger_for(conn, "bread")
        self.assertTrue(spike["outlier"])
        self.assertEqual((spike["avg_price"], spike["sample_count"]), (500.0, 3))
        self.assertEqual((known["avg_price"], known["sample_count"], known["last_price"], known["max_price"]), (500.0, 3, 5000, 500))
        self.assertEqual(len(rows), 4)
        with connect() as conn:
            early = trade.record_price(conn, item_name="cheese", unit_price=100)
            early = trade.record_price(conn, item_name="cheese", unit_price=5000)  # under three samples nothing is an outlier
        self.assertFalse(early["outlier"])
        self.assertEqual(early["sample_count"], 2)

    def test_record_price_rejects_non_positive(self):
        with connect() as conn:
            with self.assertRaises(ValueError):
                trade.record_price(conn, item_name="bread", unit_price=0)
            with self.assertRaises(ValueError):
                trade.record_price(conn, item_name="bread", unit_price=-5)
            with self.assertRaises(ValueError):
                trade.record_price(conn, item_name="bread", unit_price=5, quantity=0)
            with self.assertRaises(ValueError):
                trade.record_price(conn, item_name="", unit_price=5)
            self.assertEqual(int(conn.execute("SELECT COUNT(*) FROM price_ledger").fetchone()[0]), 0)

    def test_record_turn_prices_tags_the_seller(self):
        result = {"inventory_changes": [{"name": "rope", "quantity_delta": 1}]}
        with connect() as conn:
            out = trade.record_turn_prices(conn, result=result, narration="You pay 2 silver for the rope.",
                                           gold_note={"source": "prose_paid", "gold_delta": 0},
                                           seller={"settlement_id": "S3", "location_id": 9, "npc_id": 4}, turn=7, day=2, cset=CSET)
            row = trade.ledger_for(conn, "rope")[0]
            nothing = trade.record_turn_prices(conn, result={}, narration="", gold_note=None, seller=None, turn=7, day=2, cset=CSET)
        self.assertEqual(len(out), 1)
        self.assertEqual((out[0]["item_name"], out[0]["first"]), ("rope", True))
        self.assertEqual((row["settlement_id"], row["location_id"], row["npc_id"], row["turn"], row["day"], row["source"],
                          row["currency_set"], row["unit_price"]), ("S3", 9, 4, 7, 2, "prose_paid", "coin_medieval", 200))
        self.assertEqual(nothing, [])


class QuoteDbTests(unittest.TestCase):
    def setUp(self):
        _fresh_db()
        with connect() as conn:
            trade.record_price(conn, item_name="bread", unit_price=500, settlement_id="S1", turn=1)
            trade.record_price(conn, item_name="bread", unit_price=700, settlement_id="S1", turn=2)
            trade.record_price(conn, item_name="bread", unit_price=600, settlement_id="S2", turn=3)

    def test_settlement_price_uses_first_price_here(self):
        with connect() as conn:
            quote = trade.settlement_price(conn, "a loaf of bread", "S1", day=1, cset=CSET,
                                           multiplier={**economy.neutral_multiplier("S1", "food", day=1, reason="ok")})
        self.assertEqual((quote["basis"], quote["anchor"], quote["unit_price"], quote["known_here"]), ("ledger_first", 500, 500, True))
        self.assertEqual((quote["item_key"], quote["category"], quote["samples"], quote["quantity"], quote["total"]),
                         ("bread", "food", 3, 1, 500))
        self.assertEqual(quote["display"], "5 silver")
        self.assertEqual(set(quote), {"item_key", "item_name", "category", "unit_price", "quantity", "total", "basis", "anchor",
                                      "multiplier", "known_here", "samples", "display"})
        _assert_shape(self, quote["multiplier"], _MULTIPLIER_SHAPE)

    def test_settlement_price_first_price_survives_a_long_ledger(self):
        """The anchor is the first price ever recorded here, however many later rows the settlement holds."""
        neutral = economy.neutral_multiplier("S1", "food", day=1, reason="ok")
        with connect() as conn:
            for n in range(1001):
                trade.record_price(conn, item_name="nail", unit_price=100 + n, settlement_id="S1", turn=n)
            quote = trade.settlement_price(conn, "nail", "S1", day=1, cset=CSET, multiplier=neutral)
            elsewhere = trade.settlement_price(conn, "nail", "S2", day=1, cset=CSET, multiplier=neutral)
        self.assertEqual((quote["basis"], quote["anchor"], quote["known_here"]), ("ledger_first", 100, True))
        self.assertEqual((elsewhere["basis"], elsewhere["known_here"]), ("ledger_avg", False))

    def test_settlement_price_uses_average_elsewhere_with_multiplier(self):
        dear = {**economy.neutral_multiplier("S9", "food", day=1, reason="ok"), "mult": 1.25}
        with connect() as conn:
            quote = trade.settlement_price(conn, "bread", "S9", day=1, cset=CSET, multiplier=dear, quantity=3)
            unknown = trade.settlement_price(conn, "bread", "S9", day=1, cset=CSET, seed=SEED)
        self.assertEqual((quote["basis"], quote["anchor"], quote["unit_price"], quote["known_here"], quote["total"]),
                         ("ledger_avg", 600, 750, False, 2250))
        self.assertIn("market a little dear", trade.quote_text(quote, CSET))
        self.assertTrue(trade.quote_text(quote, CSET).startswith("bread: 7 silver, 50 copper each ("))
        # no market row for S9: the economy answers unknown_settlement and the price is unmoved
        self.assertEqual(unknown["multiplier"]["reason"], "unknown_settlement")
        self.assertEqual(unknown["unit_price"], 600)
        self.assertEqual(trade.quote_text(unknown, CSET), "bread: 6 silver each (no market data)")
        _assert_shape(self, unknown["multiplier"], _MULTIPLIER_SHAPE)

    def test_settlement_price_follows_a_real_market_row(self):
        meta = {"id": "S3", "state": "town", "population_band": "medium", "name": "Ashbarrow"}
        with connect() as conn:
            economy.ensure_settlement(conn, meta, day=1, seed=SEED)
            quote = trade.settlement_price(conn, "bread", "S3", day=1, cset=CSET, seed=SEED)
            again = trade.settlement_price(conn, "bread", "S3", day=1, cset=CSET, seed=SEED)
        self.assertEqual(quote["multiplier"]["reason"], "ok")
        self.assertEqual(quote["multiplier"]["settlement_id"], "S3")
        self.assertEqual(quote["unit_price"], currency.round_price(max(1, round(600 * quote["multiplier"]["mult"]))))
        self.assertEqual(quote, again)

    def test_settlement_price_reference_when_unknown(self):
        with connect() as conn:
            quote = trade.settlement_price(conn, "healing potion", "S9", day=1, cset=CSET, seed=SEED)
            by_category = trade.settlement_price(conn, "iron sword", "S9", day=1, cset=CSET, seed=SEED)
        self.assertEqual((quote["basis"], quote["unit_price"], quote["samples"]), ("reference", 120000, 0))
        self.assertEqual(quote["display"], "12 gold")
        self.assertEqual((by_category["basis"], by_category["category"], by_category["unit_price"]), ("reference", "weapons", 150000))

    def test_settlement_price_none_when_unknown_item_and_category(self):
        with connect() as conn:
            quote = trade.settlement_price(conn, "glowing whatsit", "S9", day=1, cset=CSET, category="relic", seed=SEED)
        self.assertEqual((quote["basis"], quote["unit_price"], quote["total"], quote["anchor"], quote["display"]),
                         ("none", 0, 0, 0, ""))
        self.assertEqual(trade.quote_text(quote, CSET), "glowing whatsit: no known price")


class OfferDbTests(unittest.TestCase):
    def setUp(self):
        _fresh_db()

    def test_open_offer_sets_code_and_expiry(self):
        with connect() as conn:
            stored = trade.open_offer(conn, _offer(turn=10))
            fetched = trade.get_offer(conn, stored["id"])
            listed = trade.open_offers(conn)
            self.assertIsNone(trade.get_offer(conn, 999))
        _assert_offer(self, stored)
        self.assertEqual(stored["id"], 1)
        self.assertEqual(stored["code"], "T1")
        self.assertEqual((stored["offered_turn"], stored["expires_turn"]), (10, 13))
        self.assertEqual(stored["status"], "offered")
        self.assertEqual(fetched, stored)
        self.assertEqual([o["id"] for o in listed], [1])
        with self.assertRaises(ValueError):
            trade.open_offer(connect(), {"kind": "steal", "item_name": "x"})

    def test_open_offer_caps_open_count(self):
        with connect() as conn:
            ids = [trade.open_offer(conn, _offer(turn=t))["id"] for t in range(1, 6)]
            listed = trade.open_offers(conn)
            first = trade.get_offer(conn, ids[0])
        self.assertEqual(len(listed), trade.MAX_OPEN_OFFERS)
        self.assertEqual([o["id"] for o in listed], [5, 4, 3, 2])  # newest first, the oldest expired
        self.assertEqual(first["status"], "expired")
        self.assertEqual(first["answered_turn"], 5)

    def test_accept_decline_withdraw_only_when_open(self):
        with connect() as conn:
            a = trade.open_offer(conn, _offer())["id"]
            b = trade.open_offer(conn, _offer())["id"]
            c = trade.open_offer(conn, _offer())["id"]
            accepted = trade.accept_offer(conn, a, turn=6)
            self.assertEqual((accepted["status"], accepted["answered_turn"], accepted["total_price"]), ("accepted", 6, 1000))
            self.assertIsNone(trade.accept_offer(conn, a, turn=7))
            self.assertIsNone(trade.decline_offer(conn, a, turn=7))
            self.assertIsNone(trade.withdraw_offer(conn, a, turn=7))
            declined = trade.decline_offer(conn, b, turn=6)
            self.assertEqual(declined["status"], "declined")
            self.assertIsNone(trade.decline_offer(conn, b, turn=7))
            refused = trade.withdraw_offer(conn, c, turn=6, reason="insulted")
            self.assertEqual((refused["status"], refused["note"]), ("refused", "insulted"))
            self.assertIsNone(trade.withdraw_offer(conn, c, turn=7))
            self.assertIsNone(trade.accept_offer(conn, 404, turn=7))
            settled = trade.mark_settled(conn, a, turn=8)
            self.assertEqual(settled["status"], "settled")
            self.assertIsNone(trade.mark_settled(conn, a, turn=8))
            self.assertIsNone(trade.mark_settled(conn, b, turn=8))
            d = trade.open_offer(conn, _offer(quantity=2, unit_price=500))["id"]
            cheaper = trade.accept_offer(conn, d, turn=9, price=800)
            self.assertEqual((cheaper["total_price"], cheaper["unit_price"], cheaper["price_basis"]), (800, 400, "counter"))
            at_table = trade.accept_offer(conn, trade.open_offer(conn, _offer(price_basis="reference"))["id"], turn=9, price=1000)
            self.assertEqual(at_table["price_basis"], "reference")  # the table price keeps its basis
            e = trade.open_offer(conn, _offer())["id"]
            with self.assertRaises(ValueError):
                trade.accept_offer(conn, e, turn=9, price=-1)
            # the rejected price left the offer open and newest
            self.assertEqual(trade.open_offers(conn)[0]["id"], e)
            self.assertEqual(trade.get_offer(conn, e)["status"], "offered")

    def test_counter_increments_rounds_and_sets_prices(self):
        with connect() as conn:
            oid = trade.open_offer(conn, _offer(quantity=2, unit_price=500))["id"]
            countered = trade.counter_offer(conn, oid, price=900, turn=6, bid=800)
            _assert_offer(self, countered)
            self.assertEqual((countered["status"], countered["counter_price"], countered["total_price"], countered["unit_price"],
                              countered["rounds"], countered["last_player_bid"], countered["asking_price"]),
                             ("countered", 900, 900, 450, 1, 800, 1000))
            self.assertEqual(countered["price_basis"], "counter")
            again = trade.counter_offer(conn, oid, price=850, turn=7, bid=820)
            self.assertEqual((again["rounds"], again["counter_price"]), (2, 850))
            taken = trade.accept_offer(conn, oid, turn=8)
            self.assertEqual(taken["total_price"], 850)  # the counter price is what is accepted
            self.assertEqual(taken["price_basis"], "counter")
            self.assertIsNone(trade.counter_offer(conn, oid, price=800, turn=9))
            with self.assertRaises(ValueError):
                trade.counter_offer(conn, trade.open_offer(conn, _offer())["id"], price=0)

    def test_expire_stale_by_turn_and_by_location(self):
        with connect() as conn:
            a = trade.open_offer(conn, _offer(turn=1, location_id=5))["id"]
            b = trade.open_offer(conn, _offer(turn=3, location_id=6))["id"]
            c = trade.open_offer(conn, _offer(turn=3, location_id=0))["id"]
            gone = trade.expire_stale(conn, turn=4, location_id=6)
            self.assertEqual(gone, [a])
            self.assertEqual(trade.get_offer(conn, a)["status"], "expired")
            self.assertEqual(trade.get_offer(conn, b)["status"], "offered")
            self.assertEqual(trade.get_offer(conn, c)["status"], "offered")
            gone = trade.expire_stale(conn, turn=4, location_id=7)
            self.assertEqual(gone, [b])  # the placeless offer only expires by time
            self.assertEqual(trade.expire_stale(conn, turn=5), [])
            self.assertEqual(trade.expire_stale(conn, turn=6), [c])
            self.assertEqual(trade.expire_stale(conn, turn=99, location_id=1), [])

    def test_state_view_shape(self):
        with connect() as conn:
            trade.open_offer(conn, _offer(turn=2, quantity=2, unit_price=500, seller_npc_id=3))
            oid = trade.open_offer(conn, _offer(item_name="cheese", turn=3))["id"]
            trade.counter_offer(conn, oid, price=900, turn=4, bid=800)
            trade.decline_offer(conn, trade.open_offer(conn, _offer(turn=4))["id"], turn=5)
            view = trade.state_view(conn, cset=CSET)
        self.assertEqual(set(view), {"open_trade_offers"})
        rows = view["open_trade_offers"]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["id"], oid)
        self.assertEqual(set(rows[0]), {"id", "code", "kind", "item_name", "quantity", "price", "units", "seller_npc_id",
                                        "status", "rounds_left", "offered_turn"})
        self.assertEqual((rows[0]["status"], rows[0]["rounds_left"], rows[0]["units"], rows[0]["price"]),
                         ("countered", 1, 900, "9 silver"))
        self.assertEqual((rows[1]["item_name"], rows[1]["quantity"], rows[1]["seller_npc_id"], rows[1]["offered_turn"],
                          rows[1]["price"], rows[1]["code"]), ("bread", 2, 3, 2, "10 silver", "T1"))
        with connect() as conn:
            for turn in range(10, 20):
                trade.open_offer(conn, _offer(turn=turn))
            many = trade.state_view(conn, cset=CSET)["open_trade_offers"]
        self.assertLessEqual(len(many), trade.STATE_VIEW_LIMIT)


class RunHaggleDbTests(unittest.TestCase):
    def setUp(self):
        _fresh_db()

    def test_run_haggle_with_seeded_rng_is_deterministic(self):
        with connect() as conn:
            location_id, npc_id = _make_keeper(conn, attitude="neutral", trust=0)
            conn.execute("INSERT INTO npc_player_relationships (npc_id, affinity) VALUES (?, 40)", (npc_id,))
            results = []
            for _ in range(2):
                oid = trade.open_offer(conn, _offer(seller_npc_id=npc_id, location_id=location_id))["id"]
                out = trade.run_haggle(conn, oid, bid=860, turn=6, cset=CSET, player_stats={"charisma": 12},
                                       player_skills=[], check_settings=None, rng=rng_for("test", seed=SEED))
                results.append(out)
            self.assertIsNone(trade.run_haggle(conn, 404, bid=1, turn=6, cset=CSET, player_stats=None, player_skills=None,
                                               check_settings=None, rng=rng_for("test", seed=SEED)))
            with self.assertRaises(ValueError):
                trade.run_haggle(conn, results[0]["offer"]["id"] or 1, bid=0, turn=6, cset=CSET, player_stats=None,
                                 player_skills=None, check_settings=None, rng=rng_for("test", seed=SEED))
        first, second = results
        self.assertEqual(set(first), {"offer", "haggle", "check"})
        _assert_offer(self, first["offer"])
        _assert_haggle(self, first["haggle"])
        self.assertEqual(first["haggle"]["band"], "Friendly")
        self.assertEqual(first["check"]["skill"]["code"], "persuasion")
        self.assertEqual(first["check"]["opposition"]["name"], "Mara")
        self.assertEqual(first["check"]["natural"], second["check"]["natural"])
        self.assertEqual(first["haggle"]["decision"], second["haggle"]["decision"])
        self.assertEqual(first["haggle"]["price"], second["haggle"]["price"])
        self.assertEqual(first["offer"]["status"], second["offer"]["status"])
        decision = first["haggle"]["decision"]
        status = first["offer"]["status"]
        expected_status = {"accept": "accepted", "counter": "countered", "insulted": "refused", "refuse": "offered"}[decision]
        self.assertEqual(status, expected_status)
        self.assertEqual(first["offer"]["last_player_bid"], 860 if decision in ("counter", "refuse") else first["offer"]["last_player_bid"])
        if decision == "accept":
            self.assertEqual(first["offer"]["total_price"], first["haggle"]["price"])
        elif decision == "counter":
            self.assertEqual((first["offer"]["counter_price"], first["offer"]["rounds"]), (first["haggle"]["price"], 1))

    def test_run_haggle_every_decision_moves_the_row_as_designed(self):
        """Scan seeds until each decision has been seen once, then check the row the decision left behind."""
        seen: dict[str, dict] = {}
        with connect() as conn:
            location_id, npc_id = _make_keeper(conn, attitude="neutral")
            conn.execute("INSERT INTO npc_player_relationships (npc_id, affinity) VALUES (?, 40)", (npc_id,))
            for seed in range(1, 200):
                if {"accept", "counter", "insulted"} <= set(seen):
                    break
                oid = trade.open_offer(conn, _offer(seller_npc_id=npc_id, location_id=location_id))["id"]
                out = trade.run_haggle(conn, oid, bid=860, turn=6, cset=CSET, player_stats={"charisma": 12},
                                       player_skills=[], check_settings=None, rng=rng_for("scan", seed=seed))
                seen.setdefault(out["haggle"]["decision"], out)
                trade.expire_stale(conn, turn=99)
        self.assertEqual({"accept", "counter", "insulted"}, {"accept", "counter", "insulted"} & set(seen), seen.keys())
        self.assertEqual(seen["accept"]["offer"]["status"], "accepted")
        self.assertEqual(seen["accept"]["offer"]["total_price"], seen["accept"]["haggle"]["price"])
        self.assertEqual(seen["counter"]["offer"]["status"], "countered")
        self.assertEqual(seen["counter"]["offer"]["rounds"], 1)
        self.assertEqual(seen["insulted"]["offer"]["status"], "refused")
        self.assertEqual(seen["insulted"]["offer"]["note"], "insulted")

    def test_run_haggle_hostile_keeper_refuses_and_spends_the_round(self):
        r = rng_for("test", seed=SEED)
        before = r.getstate()
        with connect() as conn:
            location_id, npc_id = _make_keeper(conn, attitude="hostile")
            oid = trade.open_offer(conn, _offer(seller_npc_id=npc_id, location_id=location_id))["id"]
            out = trade.run_haggle(conn, oid, bid=860, turn=6, cset=CSET, player_stats=None, player_skills=None,
                                   check_settings=None, rng=r)
        self.assertEqual((out["haggle"]["decision"], out["haggle"]["outcome"], out["haggle"]["mood"]), ("refuse", "not_rolled", "hostile"))
        self.assertEqual((out["offer"]["status"], out["offer"]["rounds"], out["offer"]["last_player_bid"]), ("offered", 1, 860))
        # the refusal came before any roll: no check, and the caller's rng was not touched
        self.assertIsNone(out["check"])
        self.assertEqual(r.getstate(), before)

    def test_run_haggle_full_price_is_taken_without_a_roll(self):
        r = rng_for("test", seed=SEED)
        before = r.getstate()
        with connect() as conn:
            location_id, npc_id = _make_keeper(conn)
            oid = trade.open_offer(conn, _offer(seller_npc_id=npc_id, location_id=location_id))["id"]
            out = trade.run_haggle(conn, oid, bid=1000, turn=6, cset=CSET, player_stats=None, player_skills=None,
                                   check_settings=None, rng=r)
        self.assertEqual((out["haggle"]["decision"], out["haggle"]["price"], out["haggle"]["outcome"]), ("accept", 1000, "not_rolled"))
        self.assertEqual((out["offer"]["status"], out["offer"]["total_price"]), ("accepted", 1000))
        self.assertIsNone(out["check"])
        self.assertEqual(r.getstate(), before)
        # a bid under the table price does roll, and the roll moves the rng
        with connect() as conn:
            oid = trade.open_offer(conn, _offer(seller_npc_id=npc_id, location_id=location_id))["id"]
            rolled = trade.run_haggle(conn, oid, bid=860, turn=7, cset=CSET, player_stats=None, player_skills=None,
                                      check_settings=None, rng=r)
        self.assertIn("natural", rolled["check"])
        self.assertNotEqual(r.getstate(), before)

    def test_run_haggle_exhausted_rounds_raises(self):
        with connect() as conn:
            location_id, npc_id = _make_keeper(conn)
            oid = trade.open_offer(conn, _offer(seller_npc_id=npc_id, location_id=location_id, max_rounds=1))["id"]
            trade.counter_offer(conn, oid, price=950, turn=6, bid=900)
            with self.assertRaises(ValueError):
                trade.run_haggle(conn, oid, bid=920, turn=7, cset=CSET, player_stats=None, player_skills=None,
                                 check_settings=None, rng=rng_for("test", seed=SEED))
            self.assertEqual(trade.get_offer(conn, oid)["status"], "countered")

    def test_run_haggle_uses_the_market_when_given_a_day(self):
        meta = {"id": "S3", "state": "town", "population_band": "medium", "name": "Ashbarrow"}
        with connect() as conn:
            economy.ensure_settlement(conn, meta, day=1, seed=SEED)
            location_id, npc_id = _make_keeper(conn)
            oid = trade.open_offer(conn, _offer(seller_npc_id=npc_id, location_id=location_id, settlement_id="S3"))["id"]
            scarce = {**economy.neutral_multiplier("S3", "food", day=1, reason="ok"), "mult": 2.0}
            out = trade.run_haggle(conn, oid, bid=990, turn=6, cset=CSET, player_stats=None, player_skills=None,
                                   check_settings=None, rng=rng_for("test", seed=SEED), multiplier=scarce)
            # a scarce market halves the Neutral ceiling of 0.10
            self.assertEqual((out["haggle"]["band"], out["haggle"]["mood"]), ("Neutral", "neutral"))
            self.assertAlmostEqual(out["haggle"]["ceiling_pct"], 0.05, places=4)
            self.assertEqual(out["haggle"]["floor"], currency.round_price(round(1000 * (1 - 0.05))))
            oid2 = trade.open_offer(conn, _offer(seller_npc_id=npc_id, location_id=location_id, settlement_id="S3"))["id"]
            out2 = trade.run_haggle(conn, oid2, bid=990, turn=6, cset=CSET, player_stats=None, player_skills=None,
                                    check_settings=None, rng=rng_for("test", seed=SEED), day=1, seed=SEED)
            market = economy.settlement_multiplier(conn, "S3", "food", day=1, seed=SEED)
            self.assertEqual(market["reason"], "ok")
            self.assertAlmostEqual(out2["haggle"]["ceiling_pct"],
                                   trade.discount_ceiling(band="Neutral", mood="neutral", multiplier=market), places=4)
            self.assertEqual(out2["haggle"]["floor"], currency.round_price(round(1000 * (1 - out2["haggle"]["ceiling_pct"]))))
            self.assertIn(out2["haggle"]["decision"], ("accept", "counter", "insulted", "refuse"))
            # without a day the market is neutral and the ceiling is the plain band value
            oid3 = trade.open_offer(conn, _offer(seller_npc_id=npc_id, location_id=location_id, settlement_id="S3"))["id"]
            out3 = trade.run_haggle(conn, oid3, bid=990, turn=6, cset=CSET, player_stats=None, player_skills=None,
                                    check_settings=None, rng=rng_for("test", seed=SEED))
            self.assertAlmostEqual(out3["haggle"]["ceiling_pct"], 0.10, places=4)

    def test_alternatives_for_fetches_rows_and_market(self):
        with connect() as conn:
            trade.record_price(conn, item_name="bread", unit_price=5000)
            trade.record_price(conn, item_name="honey cake", unit_price=14000)
            oid = trade.open_offer(conn, _offer(item_name="cheese", unit_price=10000))["id"]
            out = trade.alternatives_for(conn, oid, venue_kind="bakery", cset=CSET, day=1, seed=SEED)
            self.assertEqual(trade.alternatives_for(conn, 404, venue_kind="bakery", cset=CSET, day=1, seed=SEED), [])
        self.assertEqual([(a["kind"], a["item_key"]) for a in out], [("cheaper", "bread"), ("better", "honey cake")])


# ---------------------------------------------------------------------------
# The module stays a leaf and writes nothing foreign
# ---------------------------------------------------------------------------


class LeafTests(unittest.TestCase):
    # Sibling leaves of this pass may name app.trade (economy's docstring lists the in-cluster call,
    # agreements imports it); each must carry the unwired Status line.
    _ALLOWED_MENTIONS = {"app/economy.py", "app/agreements.py", "app/currency.py"}

    def test_module_is_a_leaf(self):
        pattern = re.compile(r"app\.trade\b|from app import trade\b|import trade\b|app/trade")
        offenders = []
        for folder in ("app", "static"):
            for path in sorted((ROOT / folder).rglob("*")):
                if not path.is_file() or path.suffix not in {".py", ".js", ".html", ".css"}:
                    continue
                rel = path.relative_to(ROOT).as_posix()
                if rel == "app/trade.py":
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
                if not pattern.search(text):
                    continue
                if rel in self._ALLOWED_MENTIONS:
                    self.assertIn("Status: built, not wired", text, f"{rel} names trade but is not an unwired leaf")
                    continue
                offenders.append(rel)
        self.assertEqual(offenders, [], f"existing code refers to app.trade: {offenders}")
        doc = trade.__doc__ or ""
        self.assertIn("Status: built, not wired (TODO n15).", doc)
        self.assertIn("Wiring (not done):", doc)
        self.assertIn("Turn on:", doc)
        self.assertIn("Tests: tests/test_trade.py", doc)
        source = (ROOT / "app" / "trade.py").read_text(encoding="utf-8")
        body = source.split('"""', 2)[2]
        self.assertNotIn("executescript", source)
        for forbidden in ("INSERT INTO journal", "UPDATE player", "UPDATE npcs", "INSERT INTO npcs", "UPDATE inventory",
                          "INSERT INTO inventory", "INSERT INTO settings", "UPDATE settings", "INSERT INTO dice_rolls",
                          "record_roll", "gm_events", "quests", "campaign_seed", "get_world_time", "pacing"):
            self.assertNotIn(forbidden, body, forbidden)
        self.assertNotIn("from app.world import", source)
        self.assertNotIn("import app.world", source)

    def test_hook_functions_named_in_docstring_exist(self):
        doc = trade.__doc__ or ""
        for name in ("apply_turn", "_settle_stated_gold", "resolve_turn_bands", "_settle_purse", "get_state",
                     "_apply_turn_npc_relationship_deltas", "_apply_inventory", "_apply_player", "_narration_text",
                     "_clear_playthrough", "_save_snapshot", "_restore_snapshot_rows"):
            self.assertIn(name, doc)
            self.assertTrue(callable(getattr(world, name)), name)
        for name in ("WORLD_TABLES", "RESTORE_ORDER", "AUTOINC_TABLES", "_REPLACE_ONLY_WHEN_EXPORTED"):
            self.assertIn(name, doc)
            self.assertTrue(hasattr(world, name), name)
        self.assertIn("open_quest_offers", doc)
        self.assertIn("apply_turn_intel", doc)
        from app import db as app_db
        from app import local_intel
        from app import main as app_main
        from app import relationships
        self.assertIn("_migrate_columns", doc)
        self.assertTrue(callable(app_db._migrate_columns))
        self.assertIn("_answer_offer", doc)
        self.assertTrue(callable(app_main._answer_offer))
        self.assertTrue(callable(local_intel.apply_turn_intel))
        self.assertTrue(callable(relationships.update_relationship))
        self.assertIn("traded_npc", relationships.RELATIONSHIP_EVENTS)
        self.assertIn("lied_to_npc_caught", relationships.RELATIONSHIP_EVENTS)
        self.assertTrue(callable(currency.active_set))
        self.assertIn("trade_offers_enabled", doc)
        self.assertIn("record_turn_prices", doc)
        self.assertIn("fulfilment_proposal", doc)
        self.assertIn("Status: built, not wired", source_text())

    def test_module_imports_nothing_heavy_at_import_time(self):
        import importlib
        import io
        import contextlib
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            importlib.reload(trade)
        self.assertEqual(buffer.getvalue(), "")

    def test_writers_touch_no_foreign_tables(self):
        _fresh_db()
        own_tables = {"price_ledger", "price_index", "trade_offers"}
        with connect() as conn:
            location_id, npc_id = _make_keeper(conn)
            get_relationship_summary(conn, npc_id)  # the documented side effect, taken before the count
            campaign_seed(conn)  # the other documented side effect: economy's seed=None fallback creates this row once
            economy.ensure_settlement(conn, {"id": "S3", "state": "town", "population_band": "medium", "name": "Ashbarrow"},
                                      day=1, seed=SEED)
            conn.execute("INSERT INTO settings (key, value) VALUES ('playthrough_options', ?)",
                         (json.dumps({"economy": "scarce"}),))
            before_counts = _table_counts(conn)
            before_settings = _setting_keys(conn)
            before_player = dict(conn.execute("SELECT * FROM player WHERE id = 1").fetchone())
            before_npc = dict(conn.execute("SELECT * FROM npcs WHERE id = ?", (npc_id,)).fetchone())
            before_rel = dict(conn.execute("SELECT * FROM npc_player_relationships WHERE npc_id = ?", (npc_id,)).fetchone())
            trade.record_price(conn, item_name="bread", unit_price=500, settlement_id="S3", npc_id=npc_id, location_id=location_id)
            trade.record_turn_prices(conn, result={"inventory_changes": [{"name": "rope", "quantity_delta": 1}]},
                                     narration="You pay 2 silver.", gold_note={"source": "prose_paid", "gold_delta": 0},
                                     seller={"settlement_id": "S3", "location_id": location_id, "npc_id": npc_id},
                                     turn=1, day=1, cset=CSET)
            trade.settlement_price(conn, "bread", "S3", day=1, cset=CSET, seed=SEED)
            trade.settlement_price(conn, "bread", "S3", day=1, cset=CSET)  # the default seed=None path, as the wiring line calls it
            a = trade.open_offer(conn, _offer(seller_npc_id=npc_id, location_id=location_id))["id"]
            b = trade.open_offer(conn, _offer(seller_npc_id=npc_id, location_id=location_id))["id"]
            c = trade.open_offer(conn, _offer(seller_npc_id=npc_id, location_id=location_id, turn=1))["id"]
            trade.run_haggle(conn, a, bid=860, turn=6, cset=CSET, player_stats={"charisma": 12}, player_skills=[],
                             check_settings=None, rng=rng_for("test", seed=SEED), day=1, seed=SEED)
            trade.counter_offer(conn, b, price=950, turn=6, bid=900)
            trade.accept_offer(conn, b, turn=7)
            trade.mark_settled(conn, b, turn=7)
            trade.alternatives_for(conn, b, venue_kind="bakery", cset=CSET, day=1, seed=SEED)
            trade.expire_stale(conn, turn=4, location_id=location_id)
            trade.state_view(conn, cset=CSET)
            trade.open_offers(conn)
            trade.known_price(conn, "bread")
            trade.ledger_for(conn, "bread")
            after_counts = _table_counts(conn)
            after_settings = _setting_keys(conn)
            after_player = dict(conn.execute("SELECT * FROM player WHERE id = 1").fetchone())
            after_npc = dict(conn.execute("SELECT * FROM npcs WHERE id = ?", (npc_id,)).fetchone())
            after_rel = dict(conn.execute("SELECT * FROM npc_player_relationships WHERE npc_id = ?", (npc_id,)).fetchone())
            self.assertEqual(trade.get_offer(conn, c)["status"], "expired")
        self.assertEqual(set(after_counts), set(before_counts))
        changed = {name for name in after_counts if after_counts[name] != before_counts.get(name)}
        self.assertEqual(changed - own_tables, set(), changed)
        self.assertGreater(after_counts["price_ledger"], 0)
        self.assertGreater(after_counts["price_index"], 0)
        self.assertGreater(after_counts["trade_offers"], 0)
        self.assertEqual(after_settings, before_settings)
        self.assertEqual(after_player, before_player)
        self.assertEqual(after_npc, before_npc)
        self.assertEqual(after_rel, before_rel)
        for name in ("player", "inventory", "npcs", "journal", "gm_events", "locations", "pacing", "quests", "dice_rolls",
                     "npc_player_relationships", "market_state", "market_events"):
            self.assertEqual(after_counts[name], before_counts[name], name)
        self.assertFalse(Path(_ENV["AI_RPG_SKILL_LIBRARY"]).exists())


def source_text() -> str:
    return (ROOT / "app" / "trade.py").read_text(encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
