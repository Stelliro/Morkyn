"""Tests for app/needs.py (TODO n16, built but not wired).

Pure tests need no database. The DB tests use a temporary file pinned through the AI_RPG_* environment
at import and again in setUpModule, so nothing here ever touches data/world.db. No model, no network,
no wall clock: every time is an abs minute handed in by the test.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-needs-test-"))
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

from app.db import connect, db_path, init_db  # noqa: E402
from app import needs  # noqa: E402


def setUpModule() -> None:
    os.environ.update(_ENV)
    assert str(db_path()).startswith(str(_TMP)), f"test isolation failed: {db_path()!r}"
    init_db()
    conn = connect()
    try:
        with conn:
            needs.ensure_schema(conn)
    finally:
        conn.close()


# contracts.md 1: the shared shapes this module produces.
_STATUS_LINE_TYPES = {"key": str, "severity": str, "line": str, "blocks": list}
_DELTA_TYPES = {"energy": int, "fatigue": int, "health": int, "energy_exact": float, "fatigue_exact": float, "health_exact": float, "reasons": list}
_RECOVERY_TYPES = {"mult": float, "factors": list, "label": str}
_FACTOR_TYPES = {"source": str, "band": str, "mult": float}
_INVENTORY_CHANGE_TYPES = {"name": str, "quantity_delta": int, "source": str, "reason": str}
_SEVERITIES = ("info", "mild", "serious", "critical")


def _state(**over):
    st = needs.default_state(0)
    st.update(over)
    return st


def _assert_shape(case, value, types):
    case.assertIsInstance(value, dict)
    case.assertEqual(set(value), set(types))
    for key, typ in types.items():
        case.assertIsInstance(value[key], typ, f"{key} should be {typ.__name__}, got {type(value[key]).__name__}")


class StateTests(unittest.TestCase):
    def test_default_state_values(self):
        st = needs.default_state(0)
        self.assertEqual(st["hunger"], 85.0)
        self.assertEqual(st["thirst"], 85.0)
        for key in ("updated_abs", "last_meal_abs", "last_drink_abs", "low_hunger_minutes", "low_thirst_minutes"):
            self.assertEqual(st[key], 0)
        self.assertEqual(st["carry"], {"energy": 0.0, "fatigue": 0.0, "health": 0.0})
        self.assertEqual(st["last_lines"], [])
        self.assertEqual(st["version"], 1)
        self.assertEqual(needs.normalize_state({}), st)

    def test_normalize_state_repairs_junk(self):
        st = needs.normalize_state({"hunger": "abc", "thirst": 250, "updated_abs": -5, "low_hunger_minutes": "12",
                                    "carry": {"energy": 5, "fatigue": "x"}, "last_lines": ["ok", 3, ""]})
        self.assertEqual(st["hunger"], 85.0)
        self.assertEqual(st["thirst"], 100.0)
        self.assertEqual(st["updated_abs"], 0)
        self.assertEqual(st["low_hunger_minutes"], 12)
        self.assertEqual(st["carry"], {"energy": 0.9999, "fatigue": 0.0, "health": 0.0})
        self.assertEqual(st["last_lines"], ["ok"])
        self.assertEqual(needs.normalize_state(None)["hunger"], 85.0)
        self.assertEqual(needs.normalize_state("junk")["thirst"], 85.0)

    def test_needs_settings_merge_and_clamp(self):
        cfg = needs.needs_settings({"needs_settings": {"start_value": 60, "hunger_rate_mult": 9, "effects_scale": -1, "enabled": "yes", "sustained_penalty": "off"}})
        self.assertEqual(cfg["start_value"], 60.0)
        self.assertEqual(cfg["hunger_rate_mult"], 3.0)
        self.assertEqual(cfg["effects_scale"], 0.0)
        self.assertTrue(cfg["enabled"])
        self.assertFalse(cfg["sustained_penalty"])
        self.assertEqual(needs.needs_settings(None), dict(needs.DEFAULT_NEEDS_SETTINGS))
        self.assertFalse(needs.DEFAULT_NEEDS_SETTINGS["enabled"])
        # contracts.md 6.3: the registered flag is playthrough_options.needs_enabled; it wins over the nested one.
        self.assertTrue(needs.needs_settings({"needs_enabled": "on"})["enabled"])
        self.assertTrue(needs.needs_settings({"needs_enabled": True, "needs_settings": {"enabled": False}})["enabled"])
        self.assertFalse(needs.needs_settings({"needs_enabled": "off", "needs_settings": {"enabled": "yes"}})["enabled"])
        self.assertTrue(needs.needs_settings({"needs_settings": {"enabled": "yes"}})["enabled"])
        self.assertFalse(needs.needs_settings({"needs_enabled": ""})["enabled"])


class BandTests(unittest.TestCase):
    def test_bands_table_boundaries(self):
        for value, key in ((100, "sated"), (75, "sated"), (74.9, "fine"), (50, "fine"), (49.9, "hungry"), (25, "hungry"),
                           (24.9, "very_hungry"), (10, "very_hungry"), (9.9, "starving"), (0, "starving")):
            self.assertEqual(needs.band_for(value, needs.HUNGER_BANDS)[0], key, value)
        for value, key in ((75, "sated"), (74.9, "fine"), (25, "thirsty"), (24.9, "parched"), (10, "parched"), (9.9, "dehydrated"), (0, "dehydrated")):
            self.assertEqual(needs.band_for(value, needs.THIRST_BANDS)[0], key, value)
        self.assertEqual(needs.hunger_band(_state(hunger=30)), "hungry")
        self.assertEqual(needs.thirst_band(_state(thirst=5)), "dehydrated")

    def test_rule_tables_match_design_numbers(self):
        self.assertEqual(needs.LOW_THRESHOLD, 25.0)
        self.assertEqual(needs.HUNGER_PER_HOUR, 2.0)
        self.assertEqual(needs.THIRST_PER_HOUR, 4.0)
        self.assertEqual(needs.ACTIVITY_MULT["travel"], 1.5)
        self.assertEqual(needs.WEATHER_THIRST_MULT["heat"], 1.6)
        self.assertEqual(needs.WEATHER_HUNGER_MULT, {"snow": 1.25, "storm": 1.1})
        self.assertEqual(needs.HUNGER_EFFECTS["starving"], {"recovery_mult": 0.35, "fatigue_per_hour": 1.0, "energy_per_hour": -0.5, "health_per_hour": -0.5, "severity": "critical"})
        self.assertEqual(needs.THIRST_EFFECTS["dehydrated"], {"recovery_mult": 0.4, "fatigue_per_hour": 2.0, "energy_per_hour": -1.5, "health_per_hour": -2.0, "severity": "critical"})
        self.assertEqual(needs.SUSTAINED_LOW, ((2880, 0.4), (720, 0.6)))
        self.assertEqual((needs.RECOVERY_MULT_FLOOR, needs.RECOVERY_MULT_CEIL), (0.1, 1.25))
        self.assertEqual(needs.FULL_REFUSE_AT, 95.0)
        for table in (needs.HUNGER_EFFECTS, needs.THIRST_EFFECTS):
            for row in table.values():
                self.assertIn(row["severity"], (None,) + _SEVERITIES)

    def test_water_words_literal(self):
        self.assertEqual(needs.WATER_WORDS, ("water", "waterskin", "water skin", "canteen", "flask", "bottle", "skin", "gourd"))


class TickTests(unittest.TestCase):
    def test_tick_rates_at_rest(self):
        r = needs.tick(needs.default_state(0), minutes=60, abs_minute=60)
        self.assertAlmostEqual(r["after"]["hunger"], 83.0)
        self.assertAlmostEqual(r["after"]["thirst"], 81.0)
        self.assertEqual(r["deltas"], needs.zero_deltas())
        self.assertEqual(r["state"]["updated_abs"], 60)
        self.assertEqual(r["minutes"], 60)
        self.assertEqual(r["bands"], {"hunger": "sated", "thirst": "sated"})
        self.assertEqual(r["lines"], [])
        _assert_shape(self, r["deltas"], _DELTA_TYPES)
        _assert_shape(self, r["recovery"], _RECOVERY_TYPES)

    def test_tick_activity_and_weather_mult(self):
        base = needs.default_state(0)
        travel = needs.tick(base, minutes=60, abs_minute=60, activity="travel")
        self.assertAlmostEqual(base["hunger"] - travel["after"]["hunger"], 3.0)
        self.assertAlmostEqual(base["thirst"] - travel["after"]["thirst"], 6.0)
        heat = needs.tick(base, minutes=60, abs_minute=60, weather={"kind": "heat"})
        self.assertAlmostEqual(base["thirst"] - heat["after"]["thirst"], 6.4)
        self.assertAlmostEqual(base["hunger"] - heat["after"]["hunger"], 2.0)
        snow = needs.tick(base, minutes=60, abs_minute=60, weather={"kind": "snow"})
        self.assertAlmostEqual(base["hunger"] - snow["after"]["hunger"], 2.5)
        odd = needs.tick(base, minutes=60, abs_minute=60, activity="juggling", weather={"kind": "ash"})
        self.assertAlmostEqual(base["hunger"] - odd["after"]["hunger"], 2.0)
        self.assertAlmostEqual(base["thirst"] - odd["after"]["thirst"], 4.0)
        scaled = needs.tick(base, minutes=60, abs_minute=60, settings={"hunger_rate_mult": 2.0})
        self.assertAlmostEqual(base["hunger"] - scaled["after"]["hunger"], 4.0)

    def test_tick_zero_or_negative_minutes_noop(self):
        st = _state(hunger=40.0, thirst=30.0, low_hunger_minutes=5)
        for minutes in (0, -10):
            r = needs.tick(st, minutes=minutes, abs_minute=999)
            self.assertEqual(r["state"], needs.normalize_state(st))
            self.assertEqual(r["deltas"], needs.zero_deltas())
            self.assertEqual(r["lines"], [])
            self.assertEqual(r["minutes"], 0)
            self.assertEqual(r["before"], r["after"])

    def test_tick_slices_across_band_boundary(self):
        r = needs.tick(_state(hunger=26.0, thirst=85.0), minutes=360, abs_minute=360)
        # One hour at hungry (0.25 fatigue) then five at very hungry (0.5 each): 2.75, not a flat 1.5.
        self.assertAlmostEqual(r["deltas"]["fatigue_exact"], 2.75)
        self.assertEqual(r["deltas"]["fatigue"], 2)
        self.assertAlmostEqual(r["deltas"]["energy_exact"], -1.25)
        self.assertEqual(r["deltas"]["energy"], -1)
        self.assertEqual(r["deltas"]["reasons"], ["hunger:hungry", "hunger:very_hungry"])
        self.assertAlmostEqual(r["after"]["hunger"], 14.0)
        self.assertEqual(r["bands"]["hunger"], "very_hungry")
        self.assertAlmostEqual(r["state"]["carry"]["fatigue"], 0.75)

    def test_tick_carry_accumulates_fractions(self):
        start = _state(hunger=85.0, thirst=40.0)
        st = start
        acc = needs.zero_deltas()
        for i in range(20):
            r = needs.tick(st, minutes=6, abs_minute=6 * (i + 1))
            st = r["state"]
            acc = needs.merge_deltas(acc, r["deltas"])
        whole = needs.tick(start, minutes=60, abs_minute=60)
        whole2 = needs.tick(whole["state"], minutes=60, abs_minute=120)
        both = needs.merge_deltas(whole["deltas"], whole2["deltas"])
        self.assertEqual(acc["fatigue"], both["fatigue"])
        self.assertEqual(both["fatigue"], 1)
        self.assertEqual(acc["energy"], both["energy"])
        self.assertAlmostEqual(st["carry"]["fatigue"], whole2["state"]["carry"]["fatigue"], places=5)
        self.assertAlmostEqual(st["thirst"], whole2["state"]["thirst"], places=3)

    def test_tick_health_loss_when_dehydrated(self):
        r = needs.tick(_state(hunger=85.0, thirst=5.0), minutes=60, abs_minute=60)
        self.assertEqual(r["deltas"]["health"], -2)
        self.assertIn(r["deltas"]["energy"], (-1, -2))
        self.assertEqual(r["deltas"]["fatigue"], 2)
        self.assertIn("thirst:dehydrated", r["deltas"]["reasons"])
        self.assertTrue(any(ln["key"] == "thirst" and ln["severity"] == "critical" for ln in r["lines"]))
        self.assertEqual(r["state"]["last_lines"], [ln["line"] for ln in r["lines"]][:4])

    def test_tick_effects_scale_setting(self):
        r = needs.tick(_state(thirst=5.0), minutes=60, abs_minute=60, settings={"effects_scale": 0.0})
        self.assertEqual(r["deltas"]["health"], 0)
        self.assertEqual(r["deltas"]["fatigue"], 0)

    def test_low_minutes_counter_and_reset(self):
        r = needs.tick(_state(hunger=20.0), minutes=120, abs_minute=120)
        self.assertEqual(r["state"]["low_hunger_minutes"], 120)
        self.assertEqual(r["state"]["low_thirst_minutes"], 0)
        r2 = needs.tick(_state(hunger=26.0), minutes=60, abs_minute=60)
        self.assertEqual(r2["state"]["low_hunger_minutes"], 30)  # 26 -> 24 crosses 25 half way through
        fed = needs.eat(r["state"], {"name": "hard bread", "quantity": 1}, abs_minute=130)
        self.assertTrue(fed["ok"])
        self.assertGreaterEqual(fed["state"]["hunger"], needs.LOW_THRESHOLD)
        self.assertEqual(fed["state"]["low_hunger_minutes"], 0)
        bite = needs.eat(r["state"], {"name": "dried apple", "quantity": 1}, abs_minute=130, portion=0.5)
        self.assertTrue(bite["ok"])
        self.assertLess(bite["state"]["hunger"], needs.LOW_THRESHOLD)
        self.assertEqual(bite["state"]["low_hunger_minutes"], 120)


class RecoveryTests(unittest.TestCase):
    def test_recovery_modifier_product_and_clamp(self):
        fine = needs.recovery_modifier(_state(hunger=60.0, thirst=60.0))
        self.assertEqual(fine, {"mult": 1.0, "factors": [], "label": ""})
        low = needs.recovery_modifier(_state(hunger=40.0, thirst=40.0))
        self.assertAlmostEqual(low["mult"], 0.765)
        self.assertEqual([f["source"] for f in low["factors"]], ["hunger", "thirst"])
        for f in low["factors"]:
            _assert_shape(self, f, _FACTOR_TYPES)
        self.assertTrue(low["label"].startswith("recovery slowed ("))
        floor = needs.recovery_modifier(_state(hunger=5.0, thirst=5.0, low_hunger_minutes=2880, low_thirst_minutes=2880))
        self.assertEqual(floor["mult"], 0.1)
        self.assertEqual([f["source"] for f in floor["factors"]], ["hunger", "thirst", "sustained_hunger", "sustained_thirst"])
        sated = needs.recovery_modifier(_state(hunger=90.0, thirst=60.0))
        self.assertAlmostEqual(sated["mult"], 1.05)
        self.assertLessEqual(sated["mult"], needs.RECOVERY_MULT_CEIL)
        self.assertTrue(sated["label"].startswith("recovery eased ("))

    def test_sustained_low_tiers(self):
        self.assertEqual(needs.recovery_modifier(_state(hunger=60.0, thirst=60.0, low_hunger_minutes=719))["mult"], 1.0)
        self.assertAlmostEqual(needs.recovery_modifier(_state(hunger=60.0, thirst=60.0, low_hunger_minutes=720))["mult"], 0.6)
        self.assertAlmostEqual(needs.recovery_modifier(_state(hunger=60.0, thirst=60.0, low_hunger_minutes=2880))["mult"], 0.4)
        off = needs.recovery_modifier(_state(hunger=60.0, thirst=60.0, low_hunger_minutes=2880), settings={"sustained_penalty": False})
        self.assertEqual(off["mult"], 1.0)
        self.assertEqual(off["factors"], [])

    def test_merge_recovery_product_clamp_and_factors(self):
        hungry = needs.recovery_modifier(_state(hunger=40.0, thirst=60.0))
        wound = {"mult": 0.8, "factors": [{"source": "wound:left_arm", "band": "infected", "mult": 0.8}], "label": "recovery slowed (wound left arm)"}
        merged = needs.merge_recovery(hungry, wound)
        self.assertAlmostEqual(merged["mult"], 0.68)
        self.assertEqual(len(merged["factors"]), 2)
        self.assertEqual(merged["label"], "recovery slowed (hunger, wound left arm)")
        _assert_shape(self, merged, _RECOVERY_TYPES)
        eased = needs.merge_recovery({"mult": 1.05, "factors": [{"source": "hunger", "band": "sated", "mult": 1.05}], "label": "x"}, {"mult": 1.0, "factors": [], "label": ""})
        self.assertAlmostEqual(eased["mult"], 1.05)
        floor = needs.merge_recovery({"mult": 0.2, "factors": [], "label": ""}, {"mult": 0.2, "factors": [], "label": ""})
        self.assertEqual(floor["mult"], 0.1)
        self.assertEqual(floor["label"], "")
        ceil = needs.merge_recovery({"mult": 1.25, "factors": [{"source": "a", "band": "b", "mult": 1.25}], "label": ""}, {"mult": 1.25, "factors": [], "label": ""})
        self.assertEqual(ceil["mult"], 1.25)

    def test_merge_deltas(self):
        a = {"energy": -1, "fatigue": 2, "health": 0, "energy_exact": -1.5, "fatigue_exact": 2.25, "health_exact": 0.0, "reasons": ["thirst:parched"]}
        b = {"energy": 0, "fatigue": 1, "health": -1, "energy_exact": -0.25, "fatigue_exact": 1.0, "health_exact": -1.0, "reasons": ["hunger:starving"]}
        m = needs.merge_deltas(a, b)
        self.assertEqual((m["energy"], m["fatigue"], m["health"]), (-1, 3, -1))
        self.assertAlmostEqual(m["energy_exact"], -1.75)
        self.assertAlmostEqual(m["fatigue_exact"], 3.25)
        self.assertEqual(m["reasons"], ["thirst:parched", "hunger:starving"])
        _assert_shape(self, m, _DELTA_TYPES)
        self.assertEqual(needs.merge_deltas(needs.zero_deltas(), needs.zero_deltas()), needs.zero_deltas())


class ClassifyTests(unittest.TestCase):
    def _cls(self, name, **over):
        row = {"name": name, "quantity": 1, "item_type": "misc", "description": ""}
        row.update(over)
        return needs.classify_item(row)

    def test_classify_food_words(self):
        bread = self._cls("hard bread")
        self.assertEqual((bread["kind"], bread["hunger_gain"], bread["food"], bread["drink"]), ("staple", 30.0, True, False))
        stew = self._cls("venison stew")
        self.assertEqual((stew["kind"], stew["hunger_gain"], stew["thirst_gain"]), ("meal", 45.0, 10.0))
        self.assertEqual(self._cls("dried apple")["kind"], "light")
        self.assertEqual(self._cls("iron bar")["kind"], "none")
        self.assertEqual(self._cls("ration bar", item_type="consumable")["kind"], "staple")
        self.assertEqual(self._cls("wolf skin", item_type="misc")["kind"], "none")
        water = self._cls("waterskin")
        self.assertEqual((water["kind"], water["thirst_gain"], water["drink"], water["food"]), ("water", 40.0, True, False))
        self.assertEqual(self._cls("lamp oil flask")["kind"], "none")
        self.assertEqual(self._cls("skin", item_type="consumable")["kind"], "water")
        self.assertEqual(self._cls("healing potion", item_type="consumable")["kind"], "none")
        self.assertEqual(self._cls("hard bread")["name"], "hard bread")

    def test_classify_by_item_type(self):
        food = self._cls("gnarl", item_type="food")
        self.assertEqual((food["kind"], food["food"], food["hunger_gain"]), ("staple", True, 30.0))
        drink = self._cls("gnarl", item_type="drink")
        self.assertEqual((drink["kind"], drink["drink"], drink["thirst_gain"]), ("water", True, 40.0))
        self.assertEqual(self._cls("gnarl", item_type="weapon")["kind"], "none")

    def test_classify_non_food_item_types_ignore_food_words(self):
        for name, item_type in (("bread knife", "weapon"), ("meat cleaver", "weapon"), ("fish hook", "tool"),
                                ("honey-coloured cloak", "clothing"), ("wine cup", "container"), ("rice sack", "backpack")):
            cls = self._cls(name, item_type=item_type)
            self.assertEqual((cls["kind"], cls["food"], cls["drink"]), ("none", False, False), name)
        rows = [{"name": "bread knife", "quantity": 1, "item_type": "weapon"}, {"name": "wine cup", "quantity": 1, "item_type": "container"},
                {"name": "fish hook", "quantity": 3, "item_type": "tool"}]
        self.assertIsNone(needs.pick_item(rows, "eat"))
        self.assertIsNone(needs.pick_item(rows, "drink"))
        self.assertEqual(needs.eat(_state(hunger=40.0), rows[0], abs_minute=10)["reason"], "not_food")
        # The same words in a consumable row still count.
        self.assertEqual(self._cls("bread knife", item_type="consumable")["kind"], "staple")

    def test_classify_named_drink_in_a_container(self):
        ale = self._cls("flask of ale", item_type="consumable")
        self.assertEqual((ale["kind"], ale["thirst_gain"], ale["hunger_gain"], ale["matched"]), ("drink", 25.0, 5.0, "ale"))
        self.assertEqual(self._cls("bottle of wine", item_type="drink")["matched"], "wine")
        self.assertEqual(self._cls("skin of milk", item_type="consumable")["thirst_gain"], 30.0)
        for name in ("waterskin", "flask", "canteen"):
            self.assertEqual(self._cls(name, item_type="consumable")["kind"], "water", name)
        self.assertEqual(needs.drink(_state(thirst=40.0), {"name": "flask of ale", "quantity": 1, "item_type": "consumable"}, abs_minute=10)["line"], "You drink the flask of ale.")

    def test_broth_is_soup_not_drink(self):
        broth = {"name": "bone broth", "quantity": 1, "item_type": "consumable"}
        self.assertEqual((self._cls("bone broth", item_type="consumable")["kind"], self._cls("bone broth", item_type="consumable")["drink"]), ("soup", False))
        self.assertEqual(needs.drink(_state(thirst=40.0), broth, abs_minute=10)["reason"], "not_drink")
        fed = needs.eat(_state(hunger=40.0, thirst=40.0), broth, abs_minute=10)
        self.assertTrue(fed["ok"])
        self.assertEqual((fed["state"]["hunger"], fed["state"]["thirst"]), (70.0, 60.0))
        self.assertFalse(any("broth" in words for words, _k, _h, _t in needs.DRINK_TABLE))

    def test_classify_description_only_for_consumables(self):
        self.assertEqual(self._cls("wedge", item_type="consumable", description="a wedge of cheese")["kind"], "staple")
        self.assertEqual(self._cls("wedge", item_type="weapon", description="a wedge of cheese")["kind"], "none")
        self.assertEqual(self._cls("wedge", item_type="", description="a wedge of cheese")["kind"], "staple")

    def test_classify_empty_stack_keeps_kind(self):
        empty = self._cls("hard bread", quantity=0)
        self.assertEqual(empty["kind"], "staple")
        self.assertFalse(empty["food"])
        self.assertFalse(empty["drink"])
        self.assertEqual(len(needs.food_items([{"name": "hard bread", "quantity": 0}])), 0)
        self.assertEqual(len(needs.food_items([{"name": "hard bread", "quantity": 2}, {"name": "waterskin", "quantity": 1}])), 1)
        self.assertEqual(len(needs.drink_items([{"name": "hard bread", "quantity": 2}, {"name": "waterskin", "quantity": 1}])), 1)


class IntentTests(unittest.TestCase):
    def test_detect_intent_eat_drink(self):
        eat = needs.detect_intent("I eat some of the bread")
        self.assertEqual((eat["action"], eat["item_hint"], eat["portion"]), ("eat", "bread", 1.0))
        sip = needs.detect_intent("take a sip from my waterskin")
        self.assertEqual((sip["action"], sip["item_hint"], sip["portion"]), ("drink", "waterskin", 0.5))
        self.assertIsNone(needs.detect_intent("I won't drink that")["action"])
        self.assertIsNone(needs.detect_intent("I refuse to eat the stew")["action"])
        self.assertIsNone(needs.detect_intent('"Eat up," she says')["action"])
        self.assertIsNone(needs.detect_intent("I look around the market")["action"])
        self.assertIsNone(needs.detect_intent("")["action"])
        both = needs.detect_intent("I eat and drink by the fire")
        self.assertEqual(both["action"], "eat")
        self.assertTrue(both["also_drink"])
        self.assertFalse(eat["also_drink"])
        self.assertEqual(needs.detect_intent("I nibble on the cheese, then rest")["item_hint"], "cheese")
        self.assertEqual(needs.detect_intent("I snack on the dried apple.")["item_hint"], "dried apple")
        self.assertEqual(set(eat), {"action", "item_hint", "portion", "also_drink"})

    def test_pick_item_prefers_hint_then_gain(self):
        rows = [
            {"name": "hard bread", "quantity": 2, "item_type": "food"},
            {"name": "venison stew", "quantity": 1, "item_type": "consumable"},
            {"name": "waterskin", "quantity": 1, "item_type": "misc"},
            {"name": "apple", "quantity": 0, "item_type": "food"},
        ]
        self.assertEqual(needs.pick_item(rows, "eat", "bread")[1]["name"], "hard bread")
        self.assertEqual(needs.pick_item(rows, "eat")[1]["name"], "venison stew")
        self.assertEqual(needs.pick_item(rows, "eat", "apple")[1]["name"], "venison stew")  # empty stack skipped, biggest gain
        self.assertEqual(needs.pick_item(rows, "drink")[1]["name"], "waterskin")
        self.assertIsNone(needs.pick_item([{"name": "iron bar", "quantity": 1}], "eat"))
        self.assertIsNone(needs.pick_item(rows, "sing"))
        self.assertIsNone(needs.pick_item([], "drink"))


class ConsumeTests(unittest.TestCase):
    BREAD = {"name": "hard bread", "quantity": 2, "item_type": "food", "description": ""}
    STEW = {"name": "venison stew", "quantity": 1, "item_type": "consumable", "description": ""}
    WATER = {"name": "waterskin", "quantity": 1, "item_type": "misc", "description": ""}

    def test_eat_consumes_one_and_raises_hunger(self):
        r = needs.eat(_state(hunger=40.0, thirst=60.0), self.BREAD, abs_minute=500)
        self.assertTrue(r["ok"])
        self.assertEqual(r["reason"], "")
        self.assertAlmostEqual(r["state"]["hunger"], 70.0)
        self.assertAlmostEqual(r["state"]["thirst"], 60.0)
        self.assertEqual(r["consume"], {"name": "hard bread", "quantity_delta": -1, "source": "needs", "reason": "eat"})
        _assert_shape(self, r["consume"], _INVENTORY_CHANGE_TYPES)
        self.assertEqual(r["state"]["last_meal_abs"], 500)
        self.assertEqual(r["state"]["updated_abs"], 500)
        self.assertEqual(r["gained"], {"hunger": 30.0, "thirst": 0.0})
        self.assertTrue(r["line"])
        self.assertIn("hard bread", r["line"])
        self.assertEqual(set(r), {"ok", "reason", "state", "consume", "gained", "line", "item"})

    def test_eat_refuses_when_full(self):
        st = _state(hunger=96.0, thirst=60.0)
        r = needs.eat(st, self.BREAD, abs_minute=10)
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason"], "not_hungry")
        self.assertIsNone(r["consume"])
        self.assertEqual(r["state"], needs.normalize_state(st))
        d = needs.drink(_state(thirst=95.0), self.WATER, abs_minute=10)
        self.assertEqual(d["reason"], "not_thirsty")

    def test_eat_refuses_non_food_and_empty_stack(self):
        r = needs.eat(_state(hunger=40.0), {"name": "iron bar", "quantity": 1, "item_type": "misc"}, abs_minute=10)
        self.assertEqual((r["ok"], r["reason"], r["consume"]), (False, "not_food", None))
        empty = needs.eat(_state(hunger=40.0), {**self.BREAD, "quantity": 0}, abs_minute=10)
        self.assertEqual((empty["ok"], empty["reason"]), (False, "none_left"))
        water = needs.eat(_state(hunger=40.0), self.WATER, abs_minute=10)
        self.assertEqual(water["reason"], "not_food")
        dry = needs.drink(_state(thirst=40.0), {**self.WATER, "quantity": 0}, abs_minute=10)
        self.assertEqual(dry["reason"], "none_left")

    def test_drink_soup_feeds_both(self):
        st = _state(hunger=40.0, thirst=40.0)
        self.assertEqual(needs.drink(st, self.STEW, abs_minute=10)["reason"], "not_drink")
        r = needs.eat(st, self.STEW, abs_minute=10)
        self.assertTrue(r["ok"])
        self.assertAlmostEqual(r["state"]["hunger"], 85.0)
        self.assertAlmostEqual(r["state"]["thirst"], 50.0)
        self.assertEqual(r["consume"]["reason"], "eat")

    def test_drink_water_and_portion(self):
        r = needs.drink(_state(thirst=20.0, low_thirst_minutes=400), self.WATER, abs_minute=77)
        self.assertTrue(r["ok"])
        self.assertAlmostEqual(r["state"]["thirst"], 60.0)
        self.assertEqual(r["state"]["last_drink_abs"], 77)
        self.assertEqual(r["state"]["low_thirst_minutes"], 0)
        self.assertEqual(r["consume"], {"name": "waterskin", "quantity_delta": -1, "source": "needs", "reason": "drink"})
        self.assertEqual(r["line"], "You drink from the waterskin.")
        half = needs.drink(_state(thirst=20.0), self.WATER, abs_minute=77, portion=0.5)
        self.assertAlmostEqual(half["state"]["thirst"], 40.0)
        capped = needs.drink(_state(thirst=90.0), self.WATER, abs_minute=77)
        self.assertEqual(capped["state"]["thirst"], 100.0)
        self.assertEqual(capped["gained"]["thirst"], 10.0)


class StatusTests(unittest.TestCase):
    def test_status_lines_empty_when_fine(self):
        for st in (_state(hunger=60.0, thirst=60.0), _state(hunger=90.0, thirst=90.0), needs.default_state(0)):
            self.assertEqual(needs.status_lines(st), [])
            self.assertEqual(needs.prompt_block(st), "")
        view = needs.state_view(_state(hunger=60.0, thirst=60.0))
        self.assertEqual(view["lines"], [])
        self.assertEqual(view["recovery_mult"], 1.0)

    def test_status_lines_and_prompt_block_when_low(self):
        st = _state(hunger=42.0, thirst=20.0, low_thirst_minutes=800)
        lines = needs.status_lines(st)
        self.assertTrue(lines)
        for ln in lines:
            _assert_shape(self, ln, _STATUS_LINE_TYPES)
            self.assertIn(ln["severity"], _SEVERITIES)
            self.assertLessEqual(len(ln["line"]), 160)
            self.assertNotIn("*", ln["line"])
        keys = [ln["key"] for ln in lines]
        self.assertIn("hunger", keys)
        self.assertIn("thirst", keys)
        self.assertIn("sustained:thirst", keys)
        self.assertIn("recovery", keys)
        ranks = [needs.SEVERITY_RANK[ln["severity"]] for ln in lines]
        self.assertEqual(ranks, sorted(ranks, reverse=True))
        self.assertTrue(all(ln["key"].split(":")[0] in ("hunger", "thirst", "sustained", "recovery") for ln in lines))
        block = needs.prompt_block(st)
        self.assertTrue(block.startswith("Player needs (server truth):\n"))
        self.assertIn("- Hunger: 42/100 (hungry)", block)
        self.assertIn("- Thirst: 20/100 (parched)", block)
        self.assertIn("- Recovery: ×0.36 (hungry, parched, long thirst)", block)
        self.assertIn("- Long thirst has worn you down; you mend slowly.", block)
        for line in block.splitlines()[1:]:
            self.assertTrue(line.startswith("- "))
        view = needs.state_view(st)
        self.assertEqual(set(view), {"hunger", "thirst", "hunger_band", "thirst_band", "hunger_label", "thirst_label", "recovery_mult",
                                     "lines", "last_meal_abs", "last_drink_abs", "low_hunger_minutes", "low_thirst_minutes"})
        self.assertEqual((view["hunger"], view["hunger_band"], view["hunger_label"]), (42, "hungry", "hungry"))
        self.assertEqual((view["thirst_band"], view["thirst_label"]), ("parched", "parched"))
        self.assertAlmostEqual(view["recovery_mult"], 0.85 * 0.7 * 0.6)
        self.assertEqual(view["low_thirst_minutes"], 800)

    def test_sustained_penalty_alone_shows_in_block(self):
        st = _state(hunger=60.0, thirst=60.0, low_hunger_minutes=3000)
        self.assertIn("Long hunger", needs.prompt_block(st))
        self.assertEqual([ln["severity"] for ln in needs.status_lines(st) if ln["key"] == "sustained:hunger"], ["critical"])


class ImportTests(unittest.TestCase):
    def test_private_helpers_still_exist(self):
        import app.player_resources as pr
        import app.prose_state as ps

        self.assertTrue(callable(getattr(pr, "_int")))
        self.assertTrue(callable(getattr(pr, "_float")))
        self.assertTrue(callable(getattr(pr, "world_abs_minutes")))
        self.assertTrue(callable(getattr(ps, "strip_negated_clauses")))
        self.assertEqual(pr.world_abs_minutes({"day": 3, "minute": 30}), 2 * 1440 + 30)

    def test_module_does_not_import_world(self):
        source = (ROOT / "app" / "needs.py").read_text(encoding="utf-8")
        self.assertNotRegex(source, r"^\s*(?:from app\.world|import app\.world|from app import world)", "needs stays light: no app.world import")
        self.assertNotIn("executescript", source)

    def test_module_is_a_leaf(self):
        needle = re.compile(r"app\.needs\b|from app import needs\b|import needs\b")
        offenders = []
        for folder in ("app", "static"):
            for path in sorted((ROOT / folder).rglob("*")):
                if not path.is_file() or path.suffix not in (".py", ".js", ".html", ".css"):
                    continue
                if path == ROOT / "app" / "needs.py":
                    continue
                try:
                    text = path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
                if needle.search(text):
                    offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual(offenders, [], "the live game must not import app.needs in this pass")
        doc = needs.__doc__ or ""
        self.assertIn("Status: built, not wired (TODO n16).", doc)
        self.assertIn("Wiring (not done):", doc)
        self.assertIn("Turn on:", doc)
        self.assertIn("Tests: tests/test_needs.py", doc)

    def test_docstring_hooks_name_real_functions(self):
        doc = needs.__doc__ or ""
        hooks = re.findall(r"(app/[\w/]+\.py):(\w+)\(\)", doc)
        self.assertGreaterEqual(len(hooks), 8)
        for rel, func in hooks:
            source = (ROOT / rel).read_text(encoding="utf-8")
            found = re.search(rf"^def {re.escape(func)}\(", source, re.M) is not None
            self.assertTrue(found, f"{rel}:{func}() is named as a hook but does not exist")


def _table_counts(conn) -> dict:
    names = [r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]
    return {name: conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0] for name in names}


def _foreign_settings(conn) -> list:
    return [tuple(r) for r in conn.execute("SELECT key, value FROM settings WHERE key != ? ORDER BY key", (needs.NEEDS_KEY,))]


class NeedsDbTests(unittest.TestCase):
    def setUp(self):
        os.environ.update(_ENV)
        path = db_path()
        if path.exists():
            path.unlink()
        init_db()
        self.conn = connect()
        with self.conn:
            needs.ensure_schema(self.conn)
            # init_db seeds player id 1 (app/db.py:674); the contract's row replaces it.
            self.conn.execute(
                "INSERT OR REPLACE INTO player (id, name, health, max_health, level, xp, gold, current_location_id) VALUES (1, 'T', 20, 20, 1, 0, 12, NULL)"
            )
            self.conn.execute("INSERT INTO inventory (code, name, quantity, item_type) VALUES ('I1', 'hard bread', 2, 'food')")
            self.conn.execute("INSERT INTO inventory (code, name, quantity, item_type) VALUES ('I2', 'waterskin', 1, 'misc')")
            self.conn.execute("INSERT INTO pacing (key, value) VALUES ('world_day', '2')")
            self.conn.execute("INSERT INTO pacing (key, value) VALUES ('world_minute', '90')")

    def tearDown(self):
        self.conn.close()

    def _rows(self):
        return [dict(r) for r in self.conn.execute("SELECT name, quantity, item_type, description FROM inventory ORDER BY id")]

    def test_ensure_schema_is_a_noop(self):
        before = [r["name"] for r in self.conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'index') ORDER BY name")]
        self.assertIsNone(needs.ensure_schema(self.conn))
        self.assertIsNone(needs.ensure_schema(self.conn))
        after = [r["name"] for r in self.conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'index') ORDER BY name")]
        self.assertEqual(before, after)

    def test_load_state_defaults_and_roundtrip(self):
        st = needs.load_state(self.conn, abs_minute=1530)
        self.assertEqual(st, needs.default_state(1530))
        self.assertIsNone(self.conn.execute("SELECT value FROM settings WHERE key = ?", (needs.NEEDS_KEY,)).fetchone())
        st["hunger"] = 33.5
        st["low_thirst_minutes"] = 90
        with self.conn:
            needs.save_state(self.conn, st)
        row = self.conn.execute("SELECT value FROM settings WHERE key = ?", (needs.NEEDS_KEY,)).fetchone()
        parsed = json.loads(row["value"])
        self.assertEqual(parsed["hunger"], 33.5)
        self.assertEqual(needs.load_state(self.conn), needs.normalize_state(st))
        st["thirst"] = 12.0
        with self.conn:
            needs.save_state(self.conn, st)
        self.assertEqual(needs.load_state(self.conn)["thirst"], 12.0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM settings WHERE key = ?", (needs.NEEDS_KEY,)).fetchone()[0], 1)

    def test_load_state_repairs_bad_row(self):
        with self.conn:
            self.conn.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (needs.NEEDS_KEY, "not json"))
        self.assertEqual(needs.load_state(self.conn, abs_minute=5), needs.default_state(5))
        with self.conn:
            self.conn.execute("UPDATE settings SET value = ? WHERE key = ?", (json.dumps({"hunger": "x", "thirst": 500}), needs.NEEDS_KEY))
        st = needs.load_state(self.conn)
        self.assertEqual((st["hunger"], st["thirst"]), (85.0, 100.0))

    def test_tick_and_save_writes_only_player_needs(self):
        counts_before = _table_counts(self.conn)
        foreign_before = _foreign_settings(self.conn)
        player_before = dict(self.conn.execute("SELECT * FROM player WHERE id = 1").fetchone())
        inv_before = self._rows()
        pacing_before = [tuple(r) for r in self.conn.execute("SELECT key, value FROM pacing ORDER BY key")]
        world_time = {"day": 2, "minute": 90}
        with self.conn:
            r = needs.tick_and_save(self.conn, minutes=60, world_time=world_time, activity="travel", weather={"kind": "heat"})
        self.assertEqual(r["minutes"], 60)
        self.assertEqual(r["state"]["updated_abs"], 1440 + 90)
        self.assertAlmostEqual(r["after"]["hunger"], 85.0 - 3.0)
        self.assertAlmostEqual(r["after"]["thirst"], 85.0 - 4.0 * 1.5 * 1.6)
        counts_after = _table_counts(self.conn)
        changed = {k for k in set(counts_before) | set(counts_after) if counts_before.get(k) != counts_after.get(k)}
        self.assertEqual(changed, {"settings"})
        self.assertEqual(counts_after["settings"], counts_before["settings"] + 1)
        self.assertEqual(_foreign_settings(self.conn), foreign_before)
        self.assertEqual(dict(self.conn.execute("SELECT * FROM player WHERE id = 1").fetchone()), player_before)
        self.assertEqual(self._rows(), inv_before)
        self.assertEqual([tuple(r) for r in self.conn.execute("SELECT key, value FROM pacing ORDER BY key")], pacing_before)
        self.assertEqual(needs.load_state(self.conn), r["state"])
        with self.conn:
            needs.tick_and_save(self.conn, minutes=30, world_time={"day": 2, "minute": 120})
        self.assertEqual(_table_counts(self.conn), counts_after)

    def test_consume_from_inventory_does_not_touch_inventory(self):
        counts_before = _table_counts(self.conn)
        with self.conn:
            needs.save_state(self.conn, _state(hunger=40.0, thirst=85.0))
        counts_before["settings"] += 1
        rows = [dict(r) for r in self.conn.execute("SELECT * FROM inventory ORDER BY id")]
        intent = needs.detect_intent("I eat some bread")
        with self.conn:
            r = needs.consume_from_inventory(self.conn, intent, rows=rows, world_time={"day": 1, "minute": 600})
        self.assertTrue(r["ok"])
        self.assertEqual(r["consume"], {"name": "hard bread", "quantity_delta": -1, "source": "needs", "reason": "eat"})
        self.assertEqual(self.conn.execute("SELECT quantity FROM inventory WHERE code = 'I1'").fetchone()[0], 2)
        self.assertEqual(_table_counts(self.conn), counts_before)
        saved = needs.load_state(self.conn)
        self.assertAlmostEqual(saved["hunger"], 70.0)
        self.assertEqual(saved["last_meal_abs"], 600)
        with self.conn:
            miss = needs.consume_from_inventory(self.conn, needs.detect_intent("I drink some ale"), rows=[], world_time={"day": 1, "minute": 601})
        self.assertEqual((miss["ok"], miss["reason"], miss["consume"]), (False, "no_item", None))
        self.assertEqual(needs.load_state(self.conn), saved)
        with self.conn:
            none = needs.consume_from_inventory(self.conn, {"action": None}, rows=rows, world_time={"day": 1, "minute": 602})
        self.assertEqual((none["ok"], none["reason"]), (False, "no_action"))
        self.assertEqual(needs.load_state(self.conn), saved)
        with self.conn:
            sip = needs.consume_from_inventory(self.conn, needs.detect_intent("take a sip from my waterskin"), rows=rows, world_time={"day": 1, "minute": 603})
        self.assertTrue(sip["ok"])
        self.assertEqual(sip["consume"]["reason"], "drink")
        self.assertEqual(self.conn.execute("SELECT quantity FROM inventory WHERE code = 'I2'").fetchone()[0], 1)
        self.assertEqual(needs.load_state(self.conn)["last_drink_abs"], 603)

    def test_consume_from_inventory_accepts_sqlite_rows(self):
        rows = list(self.conn.execute("SELECT * FROM inventory ORDER BY id"))
        with self.conn:
            needs.save_state(self.conn, _state(hunger=40.0))
            r = needs.consume_from_inventory(self.conn, {"action": "eat", "item_hint": "bread", "portion": 1.0}, rows=rows, world_time={"day": 1, "minute": 0})
        self.assertTrue(r["ok"])
        self.assertEqual(r["item"]["name"], "hard bread")

    def test_load_state_reads_needs_settings_start_value(self):
        with self.conn:
            self.conn.execute(
                "INSERT INTO settings (key, value) VALUES ('playthrough_options', ?)",
                (json.dumps({"needs_enabled": False, "needs_settings": {"start_value": 60, "thirst_rate_mult": 2.0}}),),
            )
        st = needs.load_state(self.conn)
        self.assertEqual((st["hunger"], st["thirst"]), (60.0, 60.0))
        with self.conn:
            r = needs.tick_and_save(self.conn, minutes=60, world_time={"day": 1, "minute": 60})
        self.assertAlmostEqual(r["after"]["thirst"], 60.0 - 8.0)
        self.assertAlmostEqual(r["after"]["hunger"], 58.0)
        self.assertEqual(json.loads(self.conn.execute("SELECT value FROM settings WHERE key = 'playthrough_options'").fetchone()["value"])["needs_settings"]["start_value"], 60)


if __name__ == "__main__":
    unittest.main()
