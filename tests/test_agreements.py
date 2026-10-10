"""Tests for app/agreements.py, goods-for-service agreements (TODO n18, built but not wired).

Pure rules first (work duration, material requirements, leftovers, terms, haggling, proposals, status
lines), then the lifecycle writers against a temporary database, then the leaf and no-foreign-writes
checks that keep the module unwired.

Run:  python -m unittest tests.test_agreements
"""
from __future__ import annotations

import json
import gc
import os
import re
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-agreements-test-"))
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

from app import agreements  # noqa: E402
from app import currency  # noqa: E402
from app import economy  # noqa: E402
from app import trade  # noqa: E402
from app import world  # noqa: E402
from app.db import connect, db_path, init_db  # noqa: E402
from app.player_resources import world_abs_minutes  # noqa: E402
from app.relationships import RELATIONSHIP_EVENTS  # noqa: E402

CSET = currency.theme_set("coin_medieval")
DAY = 1440


def setUpModule():
    os.environ.update(_ENV)
    init_db()
    with connect() as conn:
        agreements.ensure_schema(conn)


def _wt(day: int = 1, minute: int = 480) -> dict:
    """A world-time dict in the shape of world.format_world_time; only day and minute are read."""
    return world.format_world_time(day, minute)


def _wt_at(abs_minute: int) -> dict:
    return _wt(abs_minute // DAY + 1, abs_minute % DAY)


def _fresh_db() -> None:
    path = db_path()
    if path.exists():
        gc.collect()  # Windows will not unlink a db a leaked connection still holds
        path.unlink()
    init_db()
    with connect() as conn:
        agreements.ensure_schema(conn)
        trade.ensure_schema(conn)  # the sibling tables exist from the start so the table set is stable
        economy.ensure_schema(conn)
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


def _make_smith(conn: sqlite3.Connection, *, name: str = "Bertram") -> tuple[int, int]:
    """A locations row and an npcs row standing in it; returns (location_id, npc_id)."""
    cur = conn.execute(
        "INSERT INTO locations (code, name, kind, settlement_size) VALUES (?, ?, 'smithy', 'town')",
        (f"L{name}", f"{name}'s forge"),
    )
    location_id = int(cur.lastrowid)
    cur = conn.execute(
        "INSERT INTO npcs (code, location_id, name, role, attitude, personality, trust, rank, stat_profile) "
        "VALUES (?, ?, ?, 'smith', 'neutral', '', 0, 'F', '{}')",
        (f"N{name}", location_id, name),
    )
    return location_id, int(cur.lastrowid)


ORE = [{"item_name": "iron ore", "quantity": 15, "category": "materials"}]
BLADE = [{"item_name": "forged blade", "quantity": 1, "category": "weapons"}]


def _terms(**overrides) -> dict:
    base = dict(player_gives=ORE, counterparty_gives=BLADE, work="forge a blade", counterparty_npc_id=0,
                location_id=0, settlement_id="S3", cset=CSET)
    base.update(overrides)
    return agreements.draft_terms(**base)


_INVENTORY_CHANGE_SHAPE = {"name": str, "quantity_delta": int, "source": str, "reason": str}
_JOURNAL_SHAPE = {"kind": str, "content": str}
_EVENT_SHAPE = {"kind": str, "summary": str, "trigger": str, "due_turn": int, "force": bool, "priority": int, "payload": dict}
_STATUS_SHAPE = {"key": str, "severity": str, "line": str, "blocks": list}
_TIME_LEFT_SHAPE = {"minutes": int, "label": str, "phase": str}
_VIEW_SHAPE = {"id": int, "code": str, "status": str, "with_npc_id": int, "with_name": str, "work": str,
               "gives": str, "due_label": str, "phase": str}
_OFFER_SHAPE = {
    "id": int, "code": str, "status": str, "kind": str, "item_key": str, "item_name": str, "category": str,
    "quantity": int, "unit_price": int, "total_price": int, "asking_price": int, "currency_set": str,
    "seller_npc_id": int, "location_id": int, "settlement_id": str, "offered_turn": int, "answered_turn": int,
    "expires_turn": int, "rounds": int, "max_rounds": int, "last_player_bid": int, "counter_price": int,
    "goods_given": list, "terms_id": int, "note": str, "price_basis": str,
}


def _assert_shape(test: unittest.TestCase, value: dict, shape: dict[str, type]) -> None:
    test.assertEqual(set(value), set(shape), f"keys differ: {sorted(set(value) ^ set(shape))}")
    for key, kind in shape.items():
        test.assertIsInstance(value[key], kind, f"{key} should be {kind.__name__}, got {value[key]!r}")
        if kind is int:
            test.assertNotIsInstance(value[key], bool, key)


def _assert_inventory_changes(test: unittest.TestCase, changes: list, *, source: str = "agreement") -> None:
    test.assertIsInstance(changes, list)
    for change in changes:
        _assert_shape(test, change, _INVENTORY_CHANGE_SHAPE)
        test.assertEqual(change["source"], source)
        test.assertTrue(change["name"])
        test.assertNotEqual(change["quantity_delta"], 0)


def _assert_journal(test: unittest.TestCase, note: dict, *, kind: str = "agreement") -> None:
    _assert_shape(test, note, _JOURNAL_SHAPE)
    test.assertEqual(note["kind"], kind)
    test.assertLessEqual(len(note["kind"]), 40)
    test.assertTrue(note["content"])
    test.assertLessEqual(len(note["content"]), 900)


def _assert_event_proposal(test: unittest.TestCase, proposal: dict) -> None:
    _assert_shape(test, proposal, _EVENT_SHAPE)
    test.assertEqual(proposal["kind"], "custom")
    test.assertFalse(proposal["force"])
    test.assertEqual(proposal["priority"], 5)
    test.assertRegex(proposal["trigger"], r"^agreement:G\d+:due$")
    test.assertEqual(set(proposal["payload"]), {"agreement_id", "code", "status"})


def _assert_status_line(test: unittest.TestCase, line: dict) -> None:
    _assert_shape(test, line, _STATUS_SHAPE)
    test.assertTrue(line["key"].startswith("agreement:G"))
    test.assertIn(line["severity"], ("info", "mild", "serious", "critical"))
    test.assertLessEqual(len(line["line"]), 160)
    test.assertNotIn("\n", line["line"])
    test.assertNotIn("*", line["line"])
    test.assertEqual(line["blocks"], [])


# ---------------------------------------------------------------------------
# Pure rules
# ---------------------------------------------------------------------------


class WorkAndMaterialTests(unittest.TestCase):
    def test_estimate_work_minutes_keywords_and_defaults(self):
        self.assertEqual(agreements.estimate_work_minutes("sharpen my sword"), 120)
        self.assertEqual(agreements.estimate_work_minutes("repair the cart wheel"), 480)
        self.assertEqual(agreements.estimate_work_minutes("tan these hides"), 2880)
        self.assertEqual(agreements.estimate_work_minutes("forge a blade"), 2880)
        self.assertEqual(agreements.estimate_work_minutes("make a sword"), 2880)
        self.assertEqual(agreements.estimate_work_minutes("build a cart"), 4320)
        self.assertEqual(agreements.estimate_work_minutes("a mail shirt"), 7200)
        self.assertEqual(agreements.estimate_work_minutes("copy this chart"), 1440)
        self.assertEqual(agreements.estimate_work_minutes("set a bone"), 60)
        self.assertEqual(agreements.estimate_work_minutes("guide us to the ford"), 240)
        self.assertEqual(agreements.estimate_work_minutes("teach me the bow"), 180)
        # "reforge" is a repair word, not the forge word inside it.
        self.assertEqual(agreements.estimate_work_minutes("reforge the hilt"), 480)
        # No keyword: the category default, then the plain default.
        self.assertEqual(agreements.estimate_work_minutes("something odd", "weapons"), 2880)
        self.assertEqual(agreements.estimate_work_minutes("something odd", "armor"), 7200)
        self.assertEqual(agreements.estimate_work_minutes("something odd", "medicine"), 120)
        self.assertEqual(agreements.estimate_work_minutes("something odd", "services"), 240)
        self.assertEqual(agreements.estimate_work_minutes("something odd", "luxury"), 480)
        self.assertEqual(agreements.estimate_work_minutes("", ""), 480)
        self.assertEqual(agreements.queue_minutes(2), 960)
        self.assertEqual(agreements.queue_minutes(0), 0)

    def test_material_requirements_blade_from_ore_and_default_fraction(self):
        needed = agreements.material_requirements("forge a blade", BLADE, ORE)
        self.assertEqual(needed, [{"item_key": "iron ore", "quantity": 8}])
        # The second alternative when the player gave ingots.
        needed = agreements.material_requirements("forge a blade", BLADE, [{"item_name": "steel ingot", "quantity": 5}])
        self.assertEqual(needed, [{"item_key": "steel ingot", "quantity": 3}])
        # A multi-material product needs every material in hand; a missing one falls to the default.
        given = [{"item_name": "wood", "quantity": 4}, {"item_name": "feathers", "quantity": 2}, {"item_name": "iron", "quantity": 2}]
        needed = agreements.material_requirements("fletch arrows", [], given)
        self.assertEqual(needed, [{"item_key": "wood", "quantity": 2}, {"item_key": "feathers", "quantity": 1},
                                  {"item_key": "iron", "quantity": 1}])
        needed = agreements.material_requirements("fletch arrows", [], given[:2])
        self.assertEqual(needed, [{"item_key": "wood", "quantity": 3}, {"item_key": "feathers", "quantity": 2}])
        # An unknown product consumes ceil(0.6 x given).
        needed = agreements.material_requirements("weave a basket", [], [{"item_name": "reeds", "quantity": 10}])
        self.assertEqual(needed, [{"item_key": "reeds", "quantity": 6}])
        self.assertEqual(agreements.material_requirements("forge a blade", BLADE, []), [])
        with self.assertRaises(ValueError):
            agreements.material_requirements("forge a blade", BLADE, [{"item_name": "iron ore", "quantity": 0}])

    def test_compute_leftovers_each_policy(self):
        required = [{"item_key": "iron ore", "quantity": 8}]
        keep = agreements.compute_leftovers(ORE, required, "counterparty_keeps")
        self.assertEqual(keep["to_player"], [])
        self.assertEqual(keep["to_counterparty"], [{"item_key": "iron ore", "item_name": "iron ore", "quantity": 7}])
        back = agreements.compute_leftovers(ORE, required, "returned")
        self.assertEqual(back["to_counterparty"], [])
        self.assertEqual(back["to_player"][0]["quantity"], 7)
        split = agreements.compute_leftovers(ORE, required, "split")
        self.assertEqual(split["to_player"][0]["quantity"], 3)
        self.assertEqual(split["to_counterparty"][0]["quantity"], 4)
        lost = agreements.compute_leftovers(ORE, required, "forfeit")
        self.assertEqual(lost["to_player"], [])
        self.assertEqual(lost["to_counterparty"][0]["quantity"], 7)
        # Never below zero, and nothing listed when nothing is left.
        none = agreements.compute_leftovers(ORE, [{"item_key": "iron ore", "quantity": 20}], "returned")
        self.assertEqual(none, {"to_counterparty": [], "to_player": []})
        with self.assertRaises(ValueError):
            agreements.compute_leftovers(ORE, required, "keep_it")


class TermsTests(unittest.TestCase):
    def test_draft_terms_infers_kind_and_values(self):
        terms = _terms()
        self.assertEqual(terms["kind"], "goods_for_service")
        self.assertEqual(terms["work_minutes"], 2880)
        self.assertEqual(terms["work_category"], "weapons")
        self.assertEqual(terms["required"], [{"item_key": "iron ore", "quantity": 8}])
        self.assertEqual(terms["leftovers_policy"], "counterparty_keeps")
        self.assertEqual(terms["grace_minutes"], 1440)
        self.assertEqual(terms["currency_set"], "coin_medieval")
        self.assertEqual(terms["queue_minutes"], 0)
        self.assertEqual(set(terms["player_gives"][0]), {"item_key", "item_name", "quantity", "category"})
        # Fair value: blade (15 gold) + labour (48 h x 0.25 = 12 gold) - 7 ore kept (7 x 2 gold) = 13 gold.
        self.assertEqual(terms["value_units"], currency.from_legacy_gold(13, CSET))
        self.assertEqual(agreements.fair_value_units({**terms, "leftovers_policy": "returned"}, CSET),
                         currency.from_legacy_gold(27, CSET))
        self.assertIsInstance(terms["value_units"], int)
        # Other kinds.
        coin = _terms(player_gives=None, player_pays_units=50000)
        self.assertEqual(coin["kind"], "coin_for_service")
        swap = _terms(work="", counterparty_gives=[{"item_name": "cloak", "quantity": 1}])
        self.assertEqual(swap["kind"], "goods_for_goods")
        self.assertEqual(swap["work_minutes"], 0)
        paid = _terms(player_gives=None, counterparty_gives=None, counterparty_pays_units=30000, work="guide them to the ford")
        self.assertEqual(paid["kind"], "service_for_coin")
        self.assertEqual(paid["value_units"], currency.round_price(currency.from_legacy_gold(1, CSET)))
        # Queue from the counterparty's other jobs.
        self.assertEqual(_terms(open_jobs_for_npc=2)["queue_minutes"], 960)
        with self.assertRaises(ValueError):
            _terms(player_gives=None, counterparty_gives=None)
        with self.assertRaises(ValueError):
            _terms(player_gives=[{"item_name": "iron ore", "quantity": 0}])
        with self.assertRaises(ValueError):
            _terms(leftovers_policy="burn")
        with self.assertRaises(ValueError):
            _terms(work="", counterparty_gives=None)

    def test_terms_as_offer_is_a_trade_offer(self):
        terms = _terms(counterparty_npc_id=12, location_id=31)
        offer = agreements.terms_as_offer(terms, turn=40, cset=CSET)
        _assert_shape(self, offer, _OFFER_SHAPE)
        self.assertEqual(offer["kind"], "service")
        self.assertEqual(offer["id"], 0)
        self.assertEqual(offer["code"], "")
        self.assertEqual(offer["status"], "offered")
        self.assertEqual(offer["item_name"], "forge a blade")
        self.assertEqual(offer["asking_price"], terms["value_units"])
        self.assertEqual(offer["unit_price"], terms["value_units"])
        self.assertEqual(offer["quantity"], 1)
        self.assertEqual(offer["goods_given"], [{"item_key": "iron ore", "item_name": "iron ore", "quantity": 15}])
        self.assertEqual(offer["seller_npc_id"], 12)
        self.assertEqual(offer["location_id"], 31)
        self.assertEqual(offer["settlement_id"], "S3")
        self.assertEqual(offer["offered_turn"], 40)
        self.assertEqual(offer["currency_set"], "coin_medieval")
        self.assertEqual(offer["price_basis"], "reference")
        self.assertIn(offer["kind"], trade.OFFER_KINDS)
        swap = agreements.terms_as_offer(_terms(work="", counterparty_gives=[{"item_name": "cloak", "quantity": 1}]), turn=1, cset=CSET)
        self.assertEqual(swap["kind"], "barter")
        self.assertEqual(swap["item_name"], "cloak")
        with self.assertRaises(ValueError):
            agreements.terms_as_offer({**terms, "kind": "gift"}, turn=1, cset=CSET)

    def test_haggle_terms_accept_moves_leftovers_toward_player(self):
        terms = _terms()
        accepted = agreements.haggle_terms(terms, {"decision": "accept", "price": 100000})
        self.assertEqual(accepted["leftovers_policy"], "split")
        self.assertEqual(accepted["value_units"], 100000)
        self.assertEqual(terms["leftovers_policy"], "counterparty_keeps", "the input is not changed")
        again = agreements.haggle_terms(accepted, {"decision": "accept", "price": 90000})
        self.assertEqual(again["leftovers_policy"], "returned")
        # Exactly what the work needs: nothing to move.
        exact = _terms(player_gives=[{"item_name": "iron ore", "quantity": 8}])
        self.assertEqual(agreements.haggle_terms(exact, {"decision": "accept", "price": 1})["leftovers_policy"], "counterparty_keeps")
        # A counter asks a quarter more goods, or split instead of returned.
        countered = agreements.haggle_terms(terms, {"decision": "counter", "price": 150000})
        self.assertEqual(countered["player_gives"][0]["quantity"], 19)
        self.assertEqual(countered["value_units"], 150000)
        back = agreements.haggle_terms({**terms, "leftovers_policy": "returned"}, {"decision": "counter", "price": 150000})
        self.assertEqual(back["leftovers_policy"], "split")
        self.assertEqual(back["player_gives"][0]["quantity"], 15)
        # The known-product requirement is fixed (8 ore), but a default-fraction deal follows the raised goods.
        self.assertEqual(countered["required"], [{"item_key": "iron ore", "quantity": 8}])
        basket = _terms(player_gives=[{"item_name": "reeds", "quantity": 10}], counterparty_gives=None, work="weave a basket")
        self.assertEqual(basket["required"], [{"item_key": "reeds", "quantity": 6}])
        raised = agreements.haggle_terms(basket, {"decision": "counter", "price": 1000})
        self.assertEqual(raised["player_gives"][0]["quantity"], 13)
        self.assertEqual(raised["required"], [{"item_key": "reeds", "quantity": 8}])
        refused = agreements.haggle_terms(terms, {"decision": "refuse", "price": 0})
        self.assertEqual(refused, terms)

    def test_haggle_terms_insult_forfeits_and_slows(self):
        terms = _terms()
        insulted = agreements.haggle_terms(terms, {"decision": "insulted", "price": 143000})
        self.assertEqual(insulted["leftovers_policy"], "forfeit")
        self.assertEqual(insulted["work_minutes"], 4320)
        self.assertEqual(terms["work_minutes"], 2880)

    def test_terms_line_reads_as_one_sentence(self):
        line = agreements.terms_line(_terms(), CSET, npc_name="Bertram")
        self.assertEqual(line, "You give 15 iron ore; Bertram will forge a blade, taking 2 days; leftovers stay with Bertram.")
        line = agreements.terms_line(_terms(leftovers_policy="returned", open_jobs_for_npc=1), CSET, npc_name="Bertram")
        self.assertIn("taking 2 days 8 hours", line)
        self.assertIn("leftovers come back to you", line)
        coin = agreements.terms_line(_terms(player_gives=None, player_pays_units=50000), CSET)
        self.assertTrue(coin.startswith("You pay 5 gold; the other party will forge a blade"))
        swap = agreements.terms_line(_terms(work="", counterparty_gives=[{"item_name": "cloak", "quantity": 1}]), CSET, npc_name="Ida")
        self.assertEqual(swap, "You give 15 iron ore; Ida gives 1 cloak.")
        paid = agreements.terms_line(_terms(player_gives=None, counterparty_gives=None, counterparty_pays_units=30000,
                                            work="guide them to the ford"), CSET, npc_name="Ida")
        self.assertEqual(paid, "you will guide them to the ford; Ida pays 3 gold.")


class ProposalTests(unittest.TestCase):
    def _row(self, **overrides) -> dict:
        row = {
            "id": 3, "code": "G3", "status": "ready", "kind": "goods_for_service", "counterparty_npc_id": 12,
            "counterparty_name": "Bertram", "location_id": 31, "settlement_id": "S3", "offer_id": 0,
            "player_gives": [{"item_key": "iron ore", "item_name": "iron ore", "quantity": 15, "category": "materials"}],
            "player_pays_units": 0,
            "counterparty_gives": [{"item_key": "forged blade", "item_name": "forged blade", "quantity": 1, "category": "weapons"}],
            "counterparty_pays_units": 0, "work": "forge a blade", "work_category": "weapons", "work_minutes": 2880,
            "made_abs_minute": 480, "handed_over_abs_minute": 480, "due_abs_minute": 480 + 2880, "ready_abs_minute": 0,
            "closed_abs_minute": 0, "grace_minutes": 1440, "leftovers_policy": "split", "leftovers": {},
            "made_turn": 1, "closed_turn": 0, "currency_set": "coin_medieval", "note": "", "created_at": "",
            "required": [{"item_key": "iron ore", "quantity": 8}],
        }
        row.update(overrides)
        return row

    def test_hand_over_and_delivery_proposals_shapes(self):
        row = self._row(status="agreed", handed_over_abs_minute=0, player_pays_units=500)
        hand = agreements.hand_over_proposal(row)
        self.assertEqual(set(hand), {"inventory_changes", "money_delta_units", "journal"})
        _assert_inventory_changes(self, hand["inventory_changes"])
        self.assertEqual(hand["inventory_changes"], [{"name": "iron ore", "quantity_delta": -15, "source": "agreement", "reason": "hand_over"}])
        self.assertEqual(hand["money_delta_units"], -500)
        _assert_journal(self, hand["journal"])
        self.assertEqual(hand["journal"]["content"], "Handed 15 iron ore and paid 5 silver to Bertram for 1 forged blade.")

        delivery = agreements.delivery_proposal(self._row(counterparty_pays_units=200))
        self.assertEqual(set(delivery), {"inventory_changes", "money_delta_units", "leftovers", "relationship_event", "npc_id", "journal"})
        _assert_inventory_changes(self, delivery["inventory_changes"])
        self.assertEqual(delivery["inventory_changes"], [
            {"name": "forged blade", "quantity_delta": 1, "source": "agreement", "reason": "delivery"},
            {"name": "iron ore", "quantity_delta": 3, "source": "agreement", "reason": "delivery"},
        ])
        self.assertEqual(delivery["money_delta_units"], 200)
        self.assertEqual(delivery["leftovers"]["to_player"][0]["quantity"], 3)
        self.assertEqual(delivery["leftovers"]["to_counterparty"][0]["quantity"], 4)
        self.assertEqual(delivery["relationship_event"], "traded_npc")
        self.assertIn(delivery["relationship_event"], RELATIONSHIP_EVENTS)
        self.assertEqual(delivery["npc_id"], 12)
        _assert_journal(self, delivery["journal"])
        self.assertEqual(delivery["journal"]["content"],
                         "Bertram hands you 1 forged blade and pays 2 silver; 3 iron ore come back to you; 4 iron ore stay with Bertram.")
        # The counterparty name may be passed as an npcs row; without any name a neutral phrase stands in.
        named = agreements.delivery_proposal(self._row(counterparty_name=""), npc={"id": 12, "name": "Mara", "role": "smith"})
        self.assertTrue(named["journal"]["content"].startswith("Mara hands you"))
        bare = agreements.hand_over_proposal(self._row(counterparty_name=""))
        self.assertIn("to the other party for", bare["journal"]["content"])
        # service_for_coin: the player did the work, so the journal says so and the counterparty only pays.
        guided = agreements.delivery_proposal(self._row(
            kind="service_for_coin", counterparty_name="Ida", player_gives=[], counterparty_gives=[],
            counterparty_pays_units=30000, work="guide them to the ford", work_category="services", work_minutes=240,
            required=[], leftovers_policy="counterparty_keeps",
        ))
        self.assertEqual(guided["inventory_changes"], [])
        self.assertEqual(guided["money_delta_units"], 30000)
        _assert_journal(self, guided["journal"])
        self.assertEqual(guided["journal"]["content"], "You finish guide them to the ford for Ida; Ida pays 3 gold.")

    def test_cancel_proposal_returns_goods_unless_forfeit(self):
        # Handed over, early in the work: the goods come back.
        early = agreements.cancel_proposal(self._row(status="cancelled", closed_abs_minute=480 + 600, player_pays_units=300))
        self.assertEqual(set(early), {"inventory_changes", "money_delta_units", "returned", "reason", "journal"})
        self.assertTrue(early["returned"])
        self.assertEqual(early["reason"], "returned")
        self.assertEqual(early["inventory_changes"], [{"name": "iron ore", "quantity_delta": 15, "source": "agreement", "reason": "cancel_return"}])
        self.assertEqual(early["money_delta_units"], 300)
        _assert_journal(self, early["journal"])
        # Forfeit policy keeps them.
        lost = agreements.cancel_proposal(self._row(status="cancelled", closed_abs_minute=480 + 600, leftovers_policy="forfeit"))
        self.assertFalse(lost["returned"])
        self.assertEqual(lost["reason"], "forfeit")
        self.assertEqual(lost["inventory_changes"], [])
        self.assertEqual(lost["money_delta_units"], 0)
        # Past half the work keeps them too (judged at now_abs_minute when given).
        late = agreements.cancel_proposal(self._row(status="in_progress"), now_abs_minute=480 + 1500)
        self.assertFalse(late["returned"])
        self.assertEqual(late["reason"], "work_past_half")
        # An open row (handed over, not closed) without now_abs_minute cannot be judged and is refused.
        with self.assertRaises(ValueError):
            agreements.cancel_proposal(self._row(status="in_progress"))
        # Nothing handed over: nothing to return.
        none = agreements.cancel_proposal(self._row(status="cancelled", handed_over_abs_minute=0, closed_abs_minute=600))
        self.assertFalse(none["returned"])
        self.assertEqual(none["reason"], "nothing_handed_over")
        self.assertEqual(none["inventory_changes"], [])

    def test_status_lines_and_time_left_labels(self):
        waiting = self._row(status="in_progress")
        left = agreements.time_left(waiting, _wt_at(480 + 1200))
        _assert_shape(self, left, _TIME_LEFT_SHAPE)
        self.assertEqual(left, {"minutes": 1680, "label": "1 day 4 hours", "phase": "waiting"})
        overdue = agreements.time_left(waiting, _wt_at(480 + 2880 + 2 * DAY))
        self.assertEqual(overdue, {"minutes": -2880, "label": "overdue 2 days", "phase": "overdue"})
        ready = agreements.time_left(self._row(status="ready"), _wt_at(480 + 2880 + 30))
        self.assertEqual(ready, {"minutes": -30, "label": "ready", "phase": "ready"})
        lapsed = agreements.time_left(self._row(status="lapsed"), _wt_at(480 + 2880 + 9 * DAY))
        self.assertEqual(lapsed["phase"], "ready")
        self.assertEqual(lapsed["label"], "ready, waiting 9 days")
        # An agreed row counts to the forfeit moment (due plus grace).
        agreed = agreements.time_left(self._row(status="agreed", handed_over_abs_minute=0), _wt_at(480))
        self.assertEqual(agreed, {"minutes": 2880 + 1440, "label": "3 days", "phase": "waiting"})

        rows = [
            self._row(id=1, code="G1", status="agreed", handed_over_abs_minute=0),
            self._row(id=2, code="G2", status="in_progress"),
            self._row(id=3, code="G3", status="ready"),
            self._row(id=4, code="G4", status="lapsed"),
            self._row(id=5, code="G5", status="delivered"),
        ]
        now = _wt_at(480 + 1200)
        lines = agreements.status_lines(rows, now, CSET)
        self.assertEqual(len(lines), 4, "a closed row has no line")
        for line in lines:
            _assert_status_line(self, line)
        by_key = {line["key"]: line for line in lines}
        self.assertEqual(by_key["agreement:G1"]["severity"], "info")
        self.assertEqual(by_key["agreement:G1"]["line"], "Agreement G1 with Bertram: 15 iron ore not yet handed over; forfeits in 2 days 4 hours.")
        self.assertEqual(by_key["agreement:G2"]["severity"], "info")
        self.assertEqual(by_key["agreement:G2"]["line"], "Agreement G2 with Bertram: 1 forged blade due in 1 day 4 hours.")
        self.assertEqual(by_key["agreement:G3"]["severity"], "mild")
        self.assertEqual(by_key["agreement:G3"]["line"], "Agreement G3 with Bertram: ready; collect 1 forged blade from Bertram.")
        self.assertEqual(by_key["agreement:G4"]["severity"], "serious")
        self.assertEqual(by_key["agreement:G4"]["line"], "Agreement G4 with Bertram: lapsed; 1 forged blade is still held by Bertram.")
        self.assertNotIn("ready", by_key["agreement:G4"]["line"])
        long_lapsed = agreements.status_lines([rows[3]], _wt_at(480 + 2880 + 9 * DAY), CSET)[0]
        self.assertEqual(long_lapsed["line"],
                         "Agreement G4 with Bertram: lapsed, uncollected for 9 days; 1 forged blade is still held by Bertram.")
        late = agreements.status_lines([rows[1]], _wt_at(480 + 2880 + 2 * DAY), CSET)[0]
        self.assertEqual(late["severity"], "serious")
        self.assertEqual(late["line"], "Agreement G2 with Bertram: 1 forged blade overdue 2 days.")
        self.assertEqual(agreements.status_lines([], now, CSET), [])
        self.assertEqual(agreements.status_lines([rows[4]], now, CSET), [])

        block = agreements.prompt_block(rows[:2], now, CSET)
        self.assertTrue(block.startswith("Player agreements (server truth):\n- Agreement G1"))
        self.assertEqual(block.count("\n- "), 2)
        self.assertEqual(agreements.prompt_block([], now, CSET), "")
        self.assertEqual(agreements.prompt_block([rows[4]], now, CSET), "")


# ---------------------------------------------------------------------------
# Writers against a temporary database
# ---------------------------------------------------------------------------


class AgreementsDbTests(unittest.TestCase):
    def setUp(self):
        _fresh_db()

    def _agree(self, conn, *, npc_id: int = 0, location_id: int = 0, turn: int = 1, world_time: dict | None = None, **overrides) -> dict:
        terms = _terms(counterparty_npc_id=npc_id, location_id=location_id, **overrides)
        return agreements.agree(conn, terms=terms, turn=turn, world_time=world_time or _wt(1, 480))

    def test_schema_is_idempotent_and_cascade(self):
        with connect() as conn:
            agreements.ensure_schema(conn)
            agreements.ensure_schema(conn)
            names = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            self.assertIn("agreements", names)
            self.assertIn("agreement_events", names)
            row = self._agree(conn)
            self.assertEqual(len(agreements.events_for(conn, row["id"])), 1)
            conn.execute("DELETE FROM agreements WHERE id = ?", (row["id"],))
            self.assertEqual(agreements.events_for(conn, row["id"]), [])
        self.assertNotIn("agreements", world.WORLD_TABLES)
        self.assertNotIn("agreement_events", world.WORLD_TABLES)
        self.assertNotIn("agreements", world.AUTOINC_TABLES)

    def test_agree_sets_code_due_and_event(self):
        with connect() as conn:
            location_id, npc_id = _make_smith(conn)
            row = self._agree(conn, npc_id=npc_id, location_id=location_id, turn=7)
            self.assertEqual(row["code"], f"G{row['id']}")
            self.assertEqual(row["status"], "agreed")
            self.assertEqual(row["kind"], "goods_for_service")
            self.assertEqual(row["made_abs_minute"], 480)
            self.assertEqual(row["due_abs_minute"], 480 + 2880)
            self.assertEqual(row["work_minutes"], 2880)
            self.assertEqual(row["grace_minutes"], 1440)
            self.assertEqual(row["made_turn"], 7)
            self.assertEqual(row["counterparty_npc_id"], npc_id)
            self.assertEqual(row["counterparty_name"], "Bertram")
            self.assertEqual(row["currency_set"], "coin_medieval")
            self.assertEqual(row["player_gives"][0]["quantity"], 15)
            self.assertEqual(row["counterparty_gives"][0]["item_name"], "forged blade")
            self.assertEqual(row["required"], [{"item_key": "iron ore", "quantity": 8}])
            self.assertEqual(row["leftovers"], {})
            events = agreements.events_for(conn, row["id"])
            self.assertEqual([e["kind"] for e in events], ["agree"])
            self.assertEqual(events[0]["abs_minute"], 480)
            self.assertEqual(events[0]["turn"], 7)
            self.assertEqual(events[0]["detail"]["due_abs_minute"], 480 + 2880)
            self.assertEqual(agreements.get_agreement(conn, row["id"]), row)
            self.assertIsNone(agreements.get_agreement(conn, 999))
            listed = agreements.open_agreements(conn, npc_id=npc_id)
            self.assertEqual([r["id"] for r in listed], [row["id"]])
            self.assertEqual(agreements.open_agreements(conn, npc_id=npc_id + 1), [])
            self.assertEqual(agreements.open_agreements(conn, location_id=location_id)[0]["id"], row["id"])
            with self.assertRaises(ValueError):
                agreements.agree(conn, terms={**_terms(), "kind": "gift"}, turn=1, world_time=_wt())

    def test_queue_minutes_pushes_due_when_npc_busy(self):
        with connect() as conn:
            location_id, npc_id = _make_smith(conn)
            first = self._agree(conn, npc_id=npc_id, location_id=location_id)
            second = self._agree(conn, npc_id=npc_id, location_id=location_id)
            self.assertEqual(first["due_abs_minute"], 480 + 2880)
            self.assertEqual(second["due_abs_minute"], 480 + 480 + 2880)
            # The terms' own queue estimate wins when it is larger than what the table shows.
            third = agreements.agree(conn, terms=_terms(counterparty_npc_id=npc_id, open_jobs_for_npc=4), turn=1, world_time=_wt(1, 480))
            self.assertEqual(third["due_abs_minute"], 480 + 4 * 480 + 2880)
            # A different counterparty is not queued.
            other = self._agree(conn, npc_id=0)
            self.assertEqual(other["due_abs_minute"], 480 + 2880)

    def test_hand_over_only_from_agreed(self):
        with connect() as conn:
            row = self._agree(conn)
            moved = agreements.mark_handed_over(conn, row["id"], world_time=_wt(1, 480), turn=2)
            self.assertIsNotNone(moved)
            self.assertEqual(moved["status"], "in_progress")
            self.assertEqual(moved["handed_over_abs_minute"], 480)
            self.assertIsNone(agreements.mark_handed_over(conn, row["id"], world_time=_wt(1, 480), turn=3))
            self.assertIsNone(agreements.mark_handed_over(conn, 999, world_time=_wt(1, 480), turn=3))
            self.assertEqual([e["kind"] for e in agreements.events_for(conn, row["id"])], ["agree", "hand_over"])

    def test_hand_over_recomputes_due(self):
        with connect() as conn:
            location_id, npc_id = _make_smith(conn)
            busy = self._agree(conn, npc_id=npc_id, location_id=location_id)
            agreements.mark_handed_over(conn, busy["id"], world_time=_wt(1, 480), turn=1)
            row = self._agree(conn, npc_id=npc_id, location_id=location_id)
            self.assertEqual(row["due_abs_minute"], 480 + 480 + 2880)
            later = _wt(2, 600)  # handed over the next day
            moved = agreements.mark_handed_over(conn, row["id"], world_time=later, turn=5)
            self.assertEqual(moved["handed_over_abs_minute"], world_abs_minutes(later))
            self.assertEqual(moved["due_abs_minute"], world_abs_minutes(later) + 480 + 2880)

    def test_hand_over_counts_only_jobs_ahead(self):
        with connect() as conn:
            location_id, npc_id = _make_smith(conn)
            first = self._agree(conn, npc_id=npc_id, location_id=location_id)
            second = self._agree(conn, npc_id=npc_id, location_id=location_id)
            self.assertEqual(second["due_abs_minute"], 480 + 480 + 2880)
            # The first-made job has nothing ahead of it: the later agreement stands behind it.
            moved = agreements.mark_handed_over(conn, first["id"], world_time=_wt(1, 480), turn=2)
            self.assertEqual(moved["due_abs_minute"], 480 + 2880)
            # The second job queues behind the first, now in progress.
            moved = agreements.mark_handed_over(conn, second["id"], world_time=_wt(1, 480), turn=2)
            self.assertEqual(moved["due_abs_minute"], 480 + 480 + 2880)
            # agree() still counts every open job, whatever its order.
            third = self._agree(conn, npc_id=npc_id, location_id=location_id)
            self.assertEqual(third["due_abs_minute"], 480 + 2 * 480 + 2880)

    def test_tick_moves_in_progress_to_ready_at_due(self):
        with connect() as conn:
            row = self._agree(conn)
            agreements.mark_handed_over(conn, row["id"], world_time=_wt(1, 480), turn=1)
            due = 480 + 2880
            early = agreements.tick(conn, world_time=_wt_at(due - 1), turn=2)
            self.assertEqual(early, {"ready": [], "lapsed": [], "forfeit": [], "lines": [], "journal": [], "event_proposals": []})
            self.assertEqual(agreements.get_agreement(conn, row["id"])["status"], "in_progress")
            result = agreements.tick(conn, world_time=_wt_at(due), turn=3)
            self.assertEqual(set(result), {"ready", "lapsed", "forfeit", "lines", "journal", "event_proposals"})
            self.assertEqual(len(result["journal"]), 1)
            _assert_journal(self, result["journal"][0])
            self.assertEqual(result["journal"][0]["content"], result["lines"][0])
            self.assertEqual([r["id"] for r in result["ready"]], [row["id"]])
            self.assertEqual(result["ready"][0]["status"], "ready")
            self.assertEqual(result["ready"][0]["ready_abs_minute"], due)
            self.assertEqual(result["lapsed"], [])
            self.assertEqual(result["forfeit"], [])
            self.assertEqual(len(result["lines"]), 1)
            self.assertIn("is ready", result["lines"][0])
            self.assertEqual(len(result["event_proposals"]), 1)
            proposal = result["event_proposals"][0]
            _assert_event_proposal(self, proposal)
            self.assertEqual(proposal["trigger"], f"agreement:{row['code']}:due")
            self.assertEqual(proposal["due_turn"], 4)
            self.assertEqual(proposal["payload"], {"agreement_id": row["id"], "code": row["code"], "status": "ready"})
            self.assertEqual([e["kind"] for e in agreements.events_for(conn, row["id"])], ["agree", "hand_over", "ready"])
            # Ticking again changes nothing.
            again = agreements.tick(conn, world_time=_wt_at(due + 60), turn=4)
            self.assertEqual(again["ready"], [])
            self.assertEqual(again["lines"], [])

    def test_tick_forfeits_unhanded_after_grace(self):
        with connect() as conn:
            row = self._agree(conn)
            limit = 480 + 2880 + 1440
            kept = agreements.tick(conn, world_time=_wt_at(limit - 1), turn=2)
            self.assertEqual(kept["forfeit"], [])
            self.assertEqual(agreements.get_agreement(conn, row["id"])["status"], "agreed")
            result = agreements.tick(conn, world_time=_wt_at(limit), turn=9)
            self.assertEqual([r["id"] for r in result["forfeit"]], [row["id"]])
            stored = agreements.get_agreement(conn, row["id"])
            self.assertEqual(stored["status"], "forfeit")
            self.assertEqual(stored["closed_abs_minute"], limit)
            self.assertEqual(stored["closed_turn"], 9)
            self.assertIn("forfeit", result["lines"][0])
            self.assertEqual(len(result["journal"]), 1)
            _assert_journal(self, result["journal"][0])
            self.assertIn("is forfeit", result["journal"][0]["content"])
            _assert_event_proposal(self, result["event_proposals"][0])
            self.assertEqual(result["event_proposals"][0]["payload"]["status"], "forfeit")
            self.assertEqual(agreements.open_agreements(conn), [])

    def test_tick_lapses_ready_after_a_week(self):
        with connect() as conn:
            row = self._agree(conn)
            agreements.mark_handed_over(conn, row["id"], world_time=_wt(1, 480), turn=1)
            due = 480 + 2880
            agreements.tick(conn, world_time=_wt_at(due), turn=2)
            still = agreements.tick(conn, world_time=_wt_at(due + 7 * DAY - 1), turn=3)
            self.assertEqual(still["lapsed"], [])
            result = agreements.tick(conn, world_time=_wt_at(due + 7 * DAY), turn=4)
            self.assertEqual([r["id"] for r in result["lapsed"]], [row["id"]])
            self.assertEqual(result["lapsed"][0]["status"], "lapsed")
            self.assertIn("lapsed", result["lines"][0])
            self.assertEqual(len(result["journal"]), 1)
            _assert_journal(self, result["journal"][0])
            self.assertIn("has lapsed", result["journal"][0]["content"])
            self.assertEqual(result["event_proposals"][0]["payload"]["status"], "lapsed")
            self.assertEqual([e["kind"] for e in agreements.events_for(conn, row["id"])], ["agree", "hand_over", "ready", "lapse"])
            # A lapsed row is still open and still collectable.
            self.assertEqual([r["id"] for r in agreements.open_agreements(conn)], [row["id"]])
            # A long absence moves a row through ready and lapsed in one tick.
            other = self._agree(conn)
            agreements.mark_handed_over(conn, other["id"], world_time=_wt(1, 480), turn=5)
            jump = agreements.tick(conn, world_time=_wt_at(due + 30 * DAY), turn=6)
            self.assertEqual([r["id"] for r in jump["ready"]], [other["id"]])
            self.assertEqual([r["id"] for r in jump["lapsed"]], [other["id"]])
            self.assertEqual(agreements.get_agreement(conn, other["id"])["status"], "lapsed")

    def test_mark_delivered_from_ready_and_lapsed_only(self):
        with connect() as conn:
            row = self._agree(conn, leftovers_policy="split")
            at = _wt(1, 480)
            self.assertIsNone(agreements.mark_delivered(conn, row["id"], world_time=at, turn=2), "agreed is not deliverable")
            agreements.mark_handed_over(conn, row["id"], world_time=at, turn=2)
            self.assertIsNone(agreements.mark_delivered(conn, row["id"], world_time=at, turn=2), "in_progress is not deliverable")
            due = 480 + 2880
            agreements.tick(conn, world_time=_wt_at(due), turn=3)
            done = agreements.mark_delivered(conn, row["id"], world_time=_wt_at(due + 10), turn=4)
            self.assertEqual(done["status"], "delivered")
            self.assertEqual(done["closed_abs_minute"], due + 10)
            self.assertEqual(done["closed_turn"], 4)
            self.assertEqual(done["leftovers"]["to_player"][0]["quantity"], 3)
            self.assertEqual(done["leftovers"]["to_counterparty"][0]["quantity"], 4)
            self.assertIsNone(agreements.mark_delivered(conn, row["id"], world_time=at, turn=5))
            self.assertEqual([e["kind"] for e in agreements.events_for(conn, row["id"])], ["agree", "hand_over", "ready", "deliver"])
            # From lapsed too.
            late = self._agree(conn)
            agreements.mark_handed_over(conn, late["id"], world_time=at, turn=5)
            agreements.tick(conn, world_time=_wt_at(due + 8 * DAY), turn=6)
            self.assertEqual(agreements.get_agreement(conn, late["id"])["status"], "lapsed")
            self.assertEqual(agreements.mark_delivered(conn, late["id"], world_time=_wt_at(due + 8 * DAY), turn=7)["status"], "delivered")
            self.assertIsNone(agreements.mark_delivered(conn, 999, world_time=at, turn=7))

    def test_cancel_from_open_states_only(self):
        with connect() as conn:
            at = _wt(1, 480)
            agreed = self._agree(conn)
            cancelled = agreements.cancel(conn, agreed["id"], world_time=at, turn=2, by="player", reason="changed my mind")
            self.assertEqual(cancelled["status"], "cancelled")
            self.assertEqual(cancelled["closed_turn"], 2)
            self.assertIsNone(agreements.cancel(conn, agreed["id"], world_time=at, turn=3))
            events = agreements.events_for(conn, agreed["id"])
            self.assertEqual(events[-1]["kind"], "cancel")
            self.assertEqual(events[-1]["detail"], {"by": "player", "reason": "changed my mind"})
            working = self._agree(conn)
            agreements.mark_handed_over(conn, working["id"], world_time=at, turn=2)
            self.assertEqual(agreements.cancel(conn, working["id"], world_time=at, turn=3, by="counterparty")["status"], "cancelled")
            ready = self._agree(conn)
            agreements.mark_handed_over(conn, ready["id"], world_time=at, turn=2)
            agreements.tick(conn, world_time=_wt_at(480 + 2880), turn=3)
            self.assertIsNone(agreements.cancel(conn, ready["id"], world_time=at, turn=4), "a finished job is collected, not cancelled")
            self.assertIsNone(agreements.cancel(conn, 999, world_time=at, turn=4))
            # Dispute only from in_progress.
            disputed = self._agree(conn)
            self.assertIsNone(agreements.dispute(conn, disputed["id"], world_time=at, turn=2))
            agreements.mark_handed_over(conn, disputed["id"], world_time=at, turn=2)
            self.assertEqual(agreements.dispute(conn, disputed["id"], world_time=at, turn=3, reason="wrong steel")["status"], "disputed")
            self.assertIsNone(agreements.dispute(conn, disputed["id"], world_time=at, turn=4))
            self.assertEqual([r["id"] for r in agreements.open_agreements(conn)], [ready["id"]], "only the ready row stays open")
            for row in (cancelled, agreements.get_agreement(conn, disputed["id"])):
                self.assertIn(row["status"], agreements.TERMINAL_STATES)

    def test_state_view_shape(self):
        with connect() as conn:
            location_id, npc_id = _make_smith(conn)
            row = self._agree(conn, npc_id=npc_id, location_id=location_id, player_pays_units=500)
            view = agreements.state_view(conn, world_time=_wt(1, 480), cset=CSET)
            self.assertEqual(set(view), {"agreements"})
            self.assertEqual(len(view["agreements"]), 1)
            entry = view["agreements"][0]
            _assert_shape(self, entry, _VIEW_SHAPE)
            self.assertEqual(entry["id"], row["id"])
            self.assertEqual(entry["code"], row["code"])
            self.assertEqual(entry["status"], "agreed")
            self.assertEqual(entry["with_npc_id"], npc_id)
            self.assertEqual(entry["with_name"], "Bertram")
            self.assertEqual(entry["work"], "forge a blade")
            self.assertEqual(entry["gives"], "15 iron ore and 5 silver")
            self.assertEqual(entry["phase"], "waiting")
            self.assertEqual(entry["due_label"], "3 days")
            agreements.cancel(conn, row["id"], world_time=_wt(1, 480), turn=2)
            self.assertEqual(agreements.state_view(conn, world_time=_wt(1, 480), cset=CSET), {"agreements": []})

    def test_tick_never_raises_on_bad_row(self):
        with connect() as conn:
            good = self._agree(conn)
            agreements.mark_handed_over(conn, good["id"], world_time=_wt(1, 480), turn=1)
            bad = self._agree(conn)
            agreements.mark_handed_over(conn, bad["id"], world_time=_wt(1, 480), turn=1)
            conn.execute("UPDATE agreements SET player_gives = ? WHERE id = ?", ("{not json", bad["id"]))
            result = agreements.tick(conn, world_time=_wt_at(480 + 2880), turn=2)
            self.assertEqual([r["id"] for r in result["ready"]], [good["id"]])
            reported = [line for line in result["lines"] if f"Agreement {bad['id']} could not be ticked" in line]
            self.assertEqual(len(reported), 1)
            # The diagnostic is log text only: the journal holds the good row's entry and nothing else.
            self.assertEqual(len(result["journal"]), 1)
            _assert_journal(self, result["journal"][0])
            self.assertIn(good["code"], result["journal"][0]["content"])
            self.assertNotIn("could not be ticked", result["journal"][0]["content"])
            self.assertEqual(agreements.get_agreement(conn, bad["id"])["status"], "in_progress")
            # The lenient reader still returns the row, with the bad column as an empty list.
            self.assertEqual(agreements.get_agreement(conn, bad["id"])["player_gives"], [])

    def test_writers_touch_no_foreign_tables(self):
        with connect() as conn:
            location_id, npc_id = _make_smith(conn)
            conn.execute("INSERT INTO settings (key, value) VALUES ('playthrough_options', ?)", (json.dumps({"economy": "scarce"}),))
            conn.execute(
                "INSERT INTO inventory (code, name, quantity, item_type) VALUES ('I1', 'iron ore', 15, 'material')"
            )
            before_counts = _table_counts(conn)
            before_settings = _setting_keys(conn)
            before_player = dict(conn.execute("SELECT * FROM player WHERE id = 1").fetchone())
            before_npc = dict(conn.execute("SELECT * FROM npcs WHERE id = ?", (npc_id,)).fetchone())
            before_inventory = dict(conn.execute("SELECT * FROM inventory WHERE code = 'I1'").fetchone())
            at = _wt(1, 480)
            row = self._agree(conn, npc_id=npc_id, location_id=location_id)
            other = self._agree(conn, npc_id=npc_id, location_id=location_id)
            third = self._agree(conn, npc_id=npc_id, location_id=location_id)
            agreements.get_agreement(conn, row["id"])
            agreements.open_agreements(conn, npc_id=npc_id, location_id=location_id)
            agreements.mark_handed_over(conn, row["id"], world_time=at, turn=2)
            agreements.mark_handed_over(conn, other["id"], world_time=at, turn=2)
            agreements.tick(conn, world_time=_wt_at(480 + 480 + 2880 + 30 * DAY), turn=3)
            agreements.mark_delivered(conn, row["id"], world_time=at, turn=4)
            agreements.cancel(conn, third["id"], world_time=at, turn=4)
            agreements.events_for(conn, row["id"])
            agreements.state_view(conn, world_time=at, cset=CSET)
            after_counts = _table_counts(conn)
            self.assertEqual(_setting_keys(conn), before_settings)
            self.assertEqual(dict(conn.execute("SELECT * FROM player WHERE id = 1").fetchone()), before_player)
            self.assertEqual(dict(conn.execute("SELECT * FROM npcs WHERE id = ?", (npc_id,)).fetchone()), before_npc)
            self.assertEqual(dict(conn.execute("SELECT * FROM inventory WHERE code = 'I1'").fetchone()), before_inventory)
            own = {"agreements", "agreement_events"}
            self.assertEqual(set(after_counts), set(before_counts), "no table was created or dropped")
            changed = {name for name in before_counts if before_counts[name] != after_counts[name]}
            self.assertEqual(changed, own, f"only the module's own tables may change, got {sorted(changed)}")
            self.assertEqual(after_counts["agreements"], 3)
            self.assertGreater(after_counts["agreement_events"], 3)
            self.assertEqual(after_counts["trade_offers"], 0)
            self.assertEqual(after_counts["journal"], before_counts["journal"])
            self.assertEqual(after_counts["gm_events"], before_counts["gm_events"])


# ---------------------------------------------------------------------------
# Leaf checks
# ---------------------------------------------------------------------------


class LeafTests(unittest.TestCase):
    _ALLOWED_MENTIONS = {"app/trade.py", "app/currency.py", "app/economy.py"}

    def test_module_is_a_leaf(self):
        pattern = re.compile(r"app\.agreements\b|from app import agreements\b|import agreements\b|app/agreements")
        offenders = []
        for folder in ("app", "static"):
            for path in sorted((ROOT / folder).rglob("*")):
                if not path.is_file() or path.suffix not in {".py", ".js", ".html", ".css"}:
                    continue
                rel = path.relative_to(ROOT).as_posix()
                if rel == "app/agreements.py":
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
                if not pattern.search(text):
                    continue
                if rel in self._ALLOWED_MENTIONS:
                    self.assertIn("Status: built, not wired", text, f"{rel} names agreements but is not an unwired leaf")
                    continue
                offenders.append(rel)
        self.assertEqual(offenders, [], f"existing code refers to app.agreements: {offenders}")
        doc = agreements.__doc__ or ""
        self.assertIn("Status: built, not wired (TODO n18).", doc)
        self.assertIn("Wiring (not done):", doc)
        self.assertIn("Turn on:", doc)
        self.assertIn("Tests: tests/test_agreements.py", doc)
        source = (ROOT / "app" / "agreements.py").read_text(encoding="utf-8")
        body = source.split('"""', 2)[2]
        self.assertNotIn("executescript", source)
        for forbidden in ("INSERT INTO journal", "UPDATE player", "UPDATE npcs", "INSERT INTO npcs", "UPDATE inventory",
                          "INSERT INTO inventory", "INSERT INTO settings", "UPDATE settings", "INSERT INTO dice_rolls",
                          "trade_offers", "price_ledger", "gm_events", "quests", "campaign_seed", "get_world_time",
                          "pacing", "import random", "time.time"):
            self.assertNotIn(forbidden, body, forbidden)
        self.assertNotIn("from app.world import", source)
        self.assertNotIn("import app.world", source)
        for hook in ("app/world.py:advance_world_time()", "app/world.py:apply_turn()", "app/world.py:get_state()",
                     "app/world.py:build_prompt_context()", "app/main.py:_answer_offer()", "app/db.py:_migrate_columns()"):
            self.assertIn(hook, doc)
        # Every hook names a function that exists today.
        for module, name in (("world", "advance_world_time"), ("world", "apply_turn"), ("world", "get_state"),
                             ("world", "build_prompt_context"), ("world", "_apply_inventory"), ("world", "_turn_value"),
                             ("world", "queue_world_event")):
            self.assertTrue(callable(getattr(world, name)), f"{module}.{name} is named in the docstring but missing")
        main_src = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        self.assertIn("def _answer_offer(", main_src)
        db_src = (ROOT / "app" / "db.py").read_text(encoding="utf-8")
        self.assertIn("def _migrate_columns(", db_src)

    def test_rules_tables_match_the_design(self):
        self.assertEqual(agreements.STATES, ("agreed", "in_progress", "ready", "lapsed", "delivered", "cancelled", "forfeit", "disputed"))
        self.assertEqual(agreements.OPEN_STATES, ("agreed", "in_progress", "ready", "lapsed"))
        self.assertEqual(agreements.KINDS, ("goods_for_service", "goods_for_goods", "coin_for_service", "service_for_coin"))
        self.assertEqual(agreements.LEFTOVER_POLICIES, ("counterparty_keeps", "returned", "split", "forfeit"))
        self.assertEqual(agreements.DEFAULT_GRACE_MINUTES, 1440)
        self.assertEqual(agreements.LAPSE_AFTER_MINUTES, 7 * 1440)
        self.assertEqual(agreements.QUEUE_MINUTES_PER_JOB, 480)
        self.assertEqual(agreements.LABOUR_PER_HOUR_LEGACY_GOLD, 0.25)
        self.assertEqual(agreements.INSULT_WORK_MULT, 1.5)
        self.assertEqual(agreements.COUNTER_GOODS_RAISE, 0.25)
        self.assertEqual(agreements.DEFAULT_CONSUME_FRACTION, 0.6)
        self.assertEqual(agreements.EVENT_PRIORITY, 5)
        self.assertIn(agreements.RELATIONSHIP_EVENT_DELIVERED, RELATIONSHIP_EVENTS)
        for state in agreements.OPEN_STATES + agreements.TERMINAL_STATES:
            self.assertIn(state, agreements.STATES)
        for src, _event, dst in agreements.TRANSITIONS:
            self.assertIn(src, agreements.OPEN_STATES)
            self.assertIn(dst, agreements.STATES)
        self.assertEqual(agreements.CATEGORY_WORK_MINUTES, {
            "services": 240, "weapons": 2880, "armor": 7200, "cloth": 1440, "tools": 480, "medicine": 120,
            "knowledge": 1440, "materials": 1440, "transport": 240,
        })
        self.assertEqual([m for _, m in agreements.WORK_KEYWORD_MINUTES], [120, 480, 2880, 2880, 4320, 7200, 1440, 60, 240, 180])
        for category in agreements.CATEGORY_WORK_MINUTES:
            self.assertIn(category, economy.GOODS_CATEGORIES)


if __name__ == "__main__":
    unittest.main()
