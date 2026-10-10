"""Tests for app/currency.py (TODO n17, built but not wired).

Pure tests need no database. The DB tests use a temporary file pinned through the AI_RPG_* environment
at import and again in setUpModule, so nothing here ever touches data/world.db.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-currency-test-"))
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
from app import currency  # noqa: E402


def setUpModule() -> None:
    os.environ.update(_ENV)
    assert str(db_path()).startswith(str(_TMP)), f"test isolation failed: {db_path()!r}"
    init_db()
    conn = connect()
    try:
        with conn:
            currency.ensure_schema(conn)
    finally:
        conn.close()


MEDIEVAL = currency.theme_set("coin_medieval")
CREDITS = currency.theme_set("credits")
CASH = currency.theme_set("cash")
SCRIP = currency.theme_set("scrip")
ALL_SETS = (MEDIEVAL, CREDITS, CASH, SCRIP)

# contracts.md 1.1: the CurrencySet shape.
_SET_KEY_TYPES = {
    "id": str, "label": str, "smallest": str, "denominations": list, "generic_words": list,
    "display": str, "per_legacy_gold": int, "decimal": bool, "symbol": str, "accepts_goods": bool,
    "coin_acceptance": str, "starting_purse": int,
}
_DENOM_KEY_TYPES = {"id": str, "value": int, "singular": str, "plural": str, "short": str, "words": list}


class CurrencySetShapeTests(unittest.TestCase):
    def test_medieval_set_values_and_order(self):
        values = [d["value"] for d in MEDIEVAL["denominations"]]
        self.assertEqual(values, [1, 100, 10000, 1000000])
        self.assertEqual([d["id"] for d in MEDIEVAL["denominations"]], ["copper", "silver", "gold", "platinum"])
        self.assertEqual(MEDIEVAL["smallest"], "copper")
        self.assertEqual(MEDIEVAL["display"], "gold")
        self.assertEqual(MEDIEVAL["per_legacy_gold"], 10000)

    def test_every_preset_has_required_keys(self):
        self.assertEqual(set(currency.CURRENCY_SETS), {"coin_medieval", "credits", "cash", "scrip"})
        for cset in ALL_SETS:
            with self.subTest(set=cset["id"]):
                for key, typ in _SET_KEY_TYPES.items():
                    self.assertIn(key, cset)
                    self.assertIsInstance(cset[key], typ, key)
                self.assertIn(cset["coin_acceptance"], ("always", "usually", "sometimes"))
                denoms = cset["denominations"]
                self.assertTrue(denoms)
                self.assertEqual(denoms[0]["value"], 1)
                self.assertEqual(denoms[0]["id"], cset["smallest"])
                values = [d["value"] for d in denoms]
                self.assertEqual(values, sorted(values))
                self.assertEqual(len(set(values)), len(values))
                for denom in denoms:
                    for key, typ in _DENOM_KEY_TYPES.items():
                        self.assertIn(key, denom)
                        self.assertIsInstance(denom[key], typ, key)
                    self.assertTrue(all(isinstance(w, str) and w for w in denom["words"]))
                self.assertTrue(all(isinstance(w, str) and w for w in cset["generic_words"]))
                self.assertIsNotNone(currency.denomination(cset, cset["display"]))
                # starting_purse is today's literal 12 gold in every set.
                self.assertEqual(cset["starting_purse"], currency.from_legacy_gold(12, cset))

    def test_preset_table_numbers(self):
        self.assertEqual([(d["id"], d["value"]) for d in CREDITS["denominations"]], [("credit", 1), ("kilocredit", 1000)])
        self.assertEqual([(d["id"], d["value"]) for d in CASH["denominations"]], [("cent", 1), ("dollar", 100)])
        self.assertEqual([(d["id"], d["value"]) for d in SCRIP["denominations"]], [("scrip", 1), ("bundle", 50)])
        self.assertEqual((CREDITS["per_legacy_gold"], CASH["per_legacy_gold"], SCRIP["per_legacy_gold"]), (10, 1000, 5))
        self.assertEqual((MEDIEVAL["starting_purse"], CREDITS["starting_purse"], CASH["starting_purse"], SCRIP["starting_purse"]),
                         (120000, 120, 12000, 60))
        self.assertTrue(CASH["decimal"])
        self.assertEqual(CASH["symbol"], "$")
        self.assertTrue(SCRIP["accepts_goods"])
        self.assertEqual(SCRIP["coin_acceptance"], "sometimes")
        self.assertFalse(MEDIEVAL["accepts_goods"])
        self.assertIn("crowns", currency.denomination(MEDIEVAL, "gold")["words"])

    def test_theme_set_returns_a_copy_and_rejects_unknown(self):
        a = currency.theme_set("coin_medieval")
        a["accepts_goods"] = True
        a["denominations"][0]["words"].append("zzz")
        self.assertFalse(currency.CURRENCY_SETS["coin_medieval"]["accepts_goods"])
        self.assertNotIn("zzz", currency.CURRENCY_SETS["coin_medieval"]["denominations"][0]["words"])
        with self.assertRaises(ValueError):
            currency.theme_set("doubloons")


class ConversionTests(unittest.TestCase):
    def test_to_units_and_breakdown_roundtrip(self):
        self.assertEqual(currency.to_units(MEDIEVAL, 3, "silver"), 300)
        self.assertEqual(currency.to_units(MEDIEVAL, 12, "gold") + currency.to_units(MEDIEVAL, 34, "silver")
                         + currency.to_units(MEDIEVAL, 56, "copper"), 123456)
        parts = currency.breakdown(MEDIEVAL, 123456)
        self.assertEqual(parts, [{"id": "gold", "count": 12}, {"id": "silver", "count": 34}, {"id": "copper", "count": 56}])
        back = sum(currency.to_units(MEDIEVAL, p["count"], p["id"]) for p in parts)
        self.assertEqual(back, 123456)
        self.assertEqual(currency.breakdown(MEDIEVAL, 0), [])
        self.assertEqual(currency.breakdown(MEDIEVAL, 10000), [{"id": "gold", "count": 1}])

    def test_to_units_floats_floor_and_errors(self):
        self.assertEqual(currency.to_units(MEDIEVAL, 2.5, "gp"), 25000)
        self.assertEqual(currency.to_units(MEDIEVAL, 0.29, "silver"), 29)
        self.assertEqual(currency.to_units(CASH, 4, "bucks"), 400)
        with self.assertRaises(ValueError):
            currency.to_units(MEDIEVAL, 3, "doubloon")
        with self.assertRaises(ValueError):
            currency.to_units(MEDIEVAL, -1, "silver")

    def test_denomination_lookup(self):
        self.assertEqual(currency.denomination(MEDIEVAL, "Crowns")["id"], "gold")
        self.assertEqual(currency.denomination(MEDIEVAL, "g")["id"], "gold")
        self.assertEqual(currency.denomination(MEDIEVAL, "pennies")["id"], "copper")
        self.assertIsNone(currency.denomination(MEDIEVAL, "credit"))
        self.assertIsNone(currency.denomination(MEDIEVAL, ""))

    def test_breakdown_negative(self):
        self.assertEqual(currency.breakdown(MEDIEVAL, -10100), [{"id": "gold", "count": -1}, {"id": "silver", "count": -1}])
        self.assertEqual(currency.breakdown(SCRIP, -61), [{"id": "bundle", "count": -1}, {"id": "scrip", "count": -11}])

    def test_from_and_to_legacy_gold(self):
        self.assertEqual(currency.from_legacy_gold(12, MEDIEVAL), 120000)
        self.assertEqual(currency.from_legacy_gold(0.05, MEDIEVAL), 500)
        self.assertEqual(currency.from_legacy_gold(-7, MEDIEVAL), -70000)
        self.assertEqual(currency.to_legacy_gold(120099, MEDIEVAL), 12)
        self.assertEqual(currency.to_legacy_gold(9999, MEDIEVAL), 0)
        self.assertEqual(currency.to_legacy_gold(-5000, MEDIEVAL), 0)
        self.assertEqual(currency.to_legacy_gold(-20000, MEDIEVAL), -2)
        self.assertEqual(currency.from_legacy_gold(12, CREDITS), 120)
        self.assertEqual(currency.from_legacy_gold(12, CASH), 12000)
        self.assertEqual(currency.from_legacy_gold(12, SCRIP), 60)
        self.assertIsInstance(currency.from_legacy_gold(0.05, MEDIEVAL), int)

    def test_convert_between_sets(self):
        self.assertEqual(currency.convert(120000, MEDIEVAL, CREDITS), 120)
        self.assertEqual(currency.convert(120, CREDITS, CASH), 12000)
        self.assertEqual(currency.convert(12000, CASH, SCRIP), 60)
        self.assertEqual(currency.convert(60, SCRIP, MEDIEVAL), 120000)
        self.assertEqual(currency.convert(5, CREDITS, MEDIEVAL), 5000)
        self.assertEqual(currency.convert(-15, CREDITS, CASH), -1500)


class FormatTests(unittest.TestCase):
    def test_format_long_short_largest_display(self):
        cases = {
            # (set, units): (long, short, largest, display)
            ("coin_medieval", 123456): ("12 gold, 34 silver, 56 copper", "12g 34s 56c", "12 gold", "12.35 gold"),
            ("coin_medieval", 120000): ("12 gold", "12g", "12 gold", "12 gold"),
            ("coin_medieval", 250): ("2 silver, 50 copper", "2s 50c", "2 silver", "0.03 gold"),
            ("coin_medieval", 0): ("no copper", "no copper", "no copper", "0 gold"),
            ("coin_medieval", -70500): ("-7 gold, 5 silver", "-7g 5s", "-7 gold", "-7.05 gold"),
            ("credits", 1234): ("1,234 credits", "1,234 cr", "1 kilocredit", "1,234 credits"),
            ("credits", 1): ("1 credit", "1 cr", "1 credit", "1 credit"),
            ("credits", 0): ("no credits", "no credits", "no credits", "no credits"),
            ("credits", -40): ("-40 credits", "-40 cr", "-40 credits", "-40 credits"),
            ("cash", 1234): ("$12.34", "$12.34", "$12", "$12.34"),
            ("cash", 0): ("$0.00", "$0.00", "$0", "$0.00"),
            ("cash", -5): ("-$0.05", "-$0.05", "-$0", "-$0.05"),
            ("scrip", 1234): ("24 bundles, 34 scrip", "24b 34 scrip", "24 bundles", "1,234 scrip"),
            ("scrip", 50): ("1 bundle", "1b", "1 bundle", "50 scrip"),
            ("scrip", 0): ("no scrip", "no scrip", "no scrip", "no scrip"),
            ("scrip", -3): ("-3 scrip", "-3 scrip", "-3 scrip", "-3 scrip"),
        }
        for (set_id, units), expected in cases.items():
            cset = currency.theme_set(set_id)
            for style, want in zip(("long", "short", "largest", "display"), expected):
                with self.subTest(set=set_id, units=units, style=style):
                    self.assertEqual(currency.format_amount(units, cset, style), want)
        with self.assertRaises(ValueError):
            currency.format_amount(1, MEDIEVAL, "fancy")

    def test_format_cash_decimal(self):
        self.assertEqual(currency.format_amount(1234, CASH), "$12.34")
        self.assertEqual(currency.format_amount(5, CASH), "$0.05")
        self.assertEqual(currency.format_amount(123456, CASH), "$1,234.56")
        cset = currency.theme_set("cash")
        cset["symbol"] = "EUR "
        self.assertEqual(currency.format_amount(1234, cset), "EUR 12.34")

    def test_format_delta(self):
        self.assertEqual(currency.format_delta(200, MEDIEVAL), "+2 silver")
        self.assertEqual(currency.format_delta(-75000, MEDIEVAL), "-7 gold, 50 silver")
        self.assertEqual(currency.format_delta(0, MEDIEVAL), "no change")
        self.assertEqual(currency.format_delta(-450, CASH), "-$4.50")

    def test_purse_view_shape(self):
        view = currency.purse_view(123456, MEDIEVAL)
        self.assertEqual(set(view), {"units", "set", "display", "short", "long", "breakdown", "legacy_gold"})
        self.assertEqual(view["units"], 123456)
        self.assertEqual(view["set"], "coin_medieval")
        self.assertEqual(view["display"], "12.35 gold")
        self.assertEqual(view["short"], "12g 34s 56c")
        self.assertEqual(view["long"], "12 gold, 34 silver, 56 copper")
        self.assertEqual(view["legacy_gold"], 12)
        self.assertEqual(view["breakdown"], currency.breakdown(MEDIEVAL, 123456))
        for key in ("units", "legacy_gold"):
            self.assertIsInstance(view[key], int)
        for key in ("set", "display", "short", "long"):
            self.assertIsInstance(view[key], str)


class ParseTests(unittest.TestCase):
    def _check_shape(self, parsed):
        self.assertEqual(set(parsed), {"units", "parts", "text", "span"})
        self.assertIsInstance(parsed["units"], int)
        self.assertIsInstance(parsed["text"], str)
        self.assertEqual(len(parsed["span"]), 2)
        self.assertTrue(all(isinstance(x, int) for x in parsed["span"]))
        for part in parsed["parts"]:
            self.assertEqual(set(part), {"id", "count"})
            self.assertIsInstance(part["count"], int)

    def test_parse_simple_and_compound(self):
        one = currency.parse_amount("5 silver", MEDIEVAL)
        self._check_shape(one)
        self.assertEqual(one["units"], 500)
        self.assertEqual(one["parts"], [{"id": "silver", "count": 5}])
        self.assertEqual(one["span"], [0, 8])
        # 3 gold is 30000 copper and 20 silver is 2000, so 32000 by the set's own values.
        text = "The smith wants 3 gold and 20 silver for the blade."
        two = currency.parse_amount(text, MEDIEVAL)
        self._check_shape(two)
        self.assertEqual(two["units"], 32000)
        self.assertEqual(two["parts"], [{"id": "gold", "count": 3}, {"id": "silver", "count": 20}])
        self.assertEqual(two["text"], "3 gold and 20 silver")
        self.assertEqual(text[two["span"][0]:two["span"][1]], "3 gold and 20 silver")
        three = currency.parse_amount("He paid 3 gold, 20 silver and 5 copper for it.", MEDIEVAL)
        self.assertEqual(three["units"], 32005)
        self.assertEqual(three["text"], "3 gold, 20 silver and 5 copper")
        crowns = currency.parse_amount("That will be 7 crowns.", MEDIEVAL)
        self.assertEqual(crowns["units"], 70000)
        pieces = currency.parse_amount("two gold pieces", MEDIEVAL)
        self.assertEqual(pieces["units"], 20000)
        self.assertEqual(pieces["text"], "two gold pieces")

    def test_parse_number_words_and_generic_coins(self):
        seven = currency.parse_amount("She counts out seven coins.", MEDIEVAL)
        self.assertEqual(seven["units"], 70000)
        self.assertEqual(seven["parts"], [{"id": "gold", "count": 7}])
        self.assertIsNone(currency.parse_amount("a few coins", MEDIEVAL))
        self.assertIsNone(currency.parse_amount("", MEDIEVAL))
        self.assertIsNone(currency.parse_amount("The gold light fades.", MEDIEVAL))
        self.assertEqual(currency.parse_amount("a hundred coins", MEDIEVAL)["units"], 1000000)
        self.assertEqual(currency.parse_amount("12 money", MEDIEVAL)["units"], 120000)

    def test_parse_cash_symbol(self):
        parsed = currency.parse_amount("It costs $4.50 at the diner.", CASH)
        self._check_shape(parsed)
        self.assertEqual(parsed["units"], 450)
        self.assertEqual(parsed["text"], "$4.50")
        self.assertEqual(parsed["span"], [9, 14])
        self.assertEqual(currency.parse_amount("$12", CASH)["units"], 1200)
        self.assertEqual(currency.parse_amount("$1,250.75", CASH)["units"], 125075)
        self.assertEqual(currency.parse_amount("five bucks", CASH)["units"], 500)
        self.assertEqual(currency.parse_amount("50 cents", CASH)["units"], 50)
        self.assertIsNone(currency.parse_amount("$4.50", MEDIEVAL))

    def test_parse_credits(self):
        self.assertEqual(currency.parse_amount("2,500 credits", CREDITS)["units"], 2500)
        self.assertEqual(currency.parse_amount("pay 40 cr for the part", CREDITS)["units"], 40)
        self.assertEqual(currency.parse_amount("2 kilocredits", CREDITS)["units"], 2000)
        self.assertEqual(currency.parse_amount("ten creds", CREDITS)["units"], 10)

    def test_parse_ignores_silver_for_credits_set(self):
        self.assertIsNone(currency.parse_amount("5 silver", CREDITS))
        self.assertIsNone(currency.parse_amount("3 gold and 20 silver", CREDITS))
        self.assertIsNone(currency.parse_amount("40 credits", MEDIEVAL))
        mixed = currency.parse_amount("5 silver then 40 credits", CREDITS)
        self.assertEqual(mixed["units"], 40)
        self.assertEqual(mixed["text"], "40 credits")

    def test_parse_all_amounts(self):
        found = currency.parse_all_amounts("You pay 2 gold, then 5 silver more, and keep 3 copper.", MEDIEVAL)
        self.assertEqual([f["units"] for f in found], [20000, 500, 3])
        self.assertEqual([f["text"] for f in found], ["2 gold", "5 silver", "3 copper"])
        self.assertEqual(currency.parse_all_amounts("", MEDIEVAL), [])
        self.assertEqual(currency.parse_all_amounts("nothing here", MEDIEVAL), [])

    def test_coin_words_and_pattern(self):
        words = currency.coin_words(MEDIEVAL)
        self.assertEqual(words, sorted(set(words), key=lambda w: (-len(w), w)))
        for word in ("gold", "gold coins", "crowns", "coin", "coins", "copper", "silver", "platinum", "purse"):
            self.assertIn(word, words)
        self.assertNotIn("g", words)
        pattern = re.compile(currency.coin_pattern(MEDIEVAL), re.I)
        self.assertTrue(pattern.match("Gold coins"))
        self.assertIsNone(pattern.match("goldfish"))
        self.assertIsNone(re.compile(currency.coin_pattern(CREDITS), re.I).match("silver"))

    def test_coin_pattern_matches_prose_state_words(self):
        from app import prose_state

        self.assertTrue(hasattr(prose_state, "_COIN"), "prose_state._COIN moved; update the design note")
        self.assertTrue(hasattr(prose_state, "_NUMBER_WORDS"), "prose_state._NUMBER_WORDS moved; currency imports it")
        legacy = re.compile(prose_state._COIN, re.I)
        ours = re.compile(currency.coin_pattern(MEDIEVAL), re.I)
        for phrase in ("gold", "gold coin", "gold coins", "gold piece", "gold pieces", "gold crown", "gold crowns",
                       "coin", "coins", "crown", "crowns"):
            with self.subTest(phrase=phrase):
                self.assertTrue(legacy.match(phrase), "the legacy regex no longer reads this phrase")
                self.assertTrue(ours.match(phrase))
        self.assertEqual(currency.parse_amount("7 gold crowns", MEDIEVAL)["units"], 70000)


class ThemeDetectionTests(unittest.TestCase):
    def test_detect_theme_set_table(self):
        self.assertTrue(hasattr(__import__("app.world", fromlist=["resolve_world_era"]), "resolve_world_era"))
        self.assertEqual(currency.detect_theme_set(None), "coin_medieval")
        self.assertEqual(currency.detect_theme_set({}), "coin_medieval")
        self.assertEqual(currency.detect_theme_set({"world_style": "frontier dark fantasy"}), "coin_medieval")
        self.assertEqual(currency.detect_theme_set({"world_style": "low magic mercantile city", "tech_level": "iron age"}), "coin_medieval")
        # The setup form stores the tech level beside the style; the style words alone do not say "future".
        self.assertEqual(currency.detect_theme_set({"world_style": "space frontier salvage", "tech_level": "spacefaring salvage"}), "credits")
        self.assertEqual(currency.detect_theme_set({"custom_style": "an orbital station in cyberpunk decay"}), "credits")
        self.assertEqual(currency.detect_theme_set({"world_style": "post-collapse settlement"}), "scrip")
        self.assertEqual(currency.detect_theme_set({"custom_style": "life after the fall", "tech_level": "near future"}), "scrip")
        self.assertEqual(currency.detect_theme_set({"tech_level": "near future"}), "cash")
        self.assertEqual(currency.detect_theme_set({"tech_level": "early industrial"}), "cash")
        self.assertEqual(currency.detect_theme_set({"world_style": "frontier dark fantasy", "economy": "barter-heavy"}), "coin_medieval")
        self.assertEqual(currency.detect_theme_set({"tech_level": "near future", "economy": "barter"}), "scrip")
        self.assertEqual(currency.detect_theme_set({"tech_level": "spacefaring salvage", "economy": "barter-heavy"}), "scrip")
        self.assertEqual(currency.detect_theme_set({"world_style": None, "economy": 5}), "coin_medieval")

    def test_barter_forces_goods_on_a_coin_world(self):
        cset = currency.set_for_options({"world_style": "frontier dark fantasy", "economy": "barter-heavy"})
        self.assertEqual(cset["id"], "coin_medieval")
        self.assertTrue(cset["accepts_goods"])
        self.assertFalse(currency.CURRENCY_SETS["coin_medieval"]["accepts_goods"])
        plain = currency.set_for_options({"world_style": "frontier dark fantasy", "economy": "scarce"})
        self.assertFalse(plain["accepts_goods"])


class RoundPriceTests(unittest.TestCase):
    def test_round_price_table(self):
        for value, want in ((0, 0), (1, 1), (99, 99), (100, 100), (999, 999), (1234, 1230), (1235, 1240),
                            (123456, 123000), (123499, 123000), (123500, 124000), (1000000, 1000000), (-1234, -1230)):
            with self.subTest(value=value):
                self.assertEqual(currency.round_price(value), want)
        self.assertGreaterEqual(currency.round_price(100), 1)


class MigrationPlanTests(unittest.TestCase):
    def test_migration_plan_is_documented(self):
        self.assertEqual(len(currency.MIGRATION_PLAN), 12)
        self.assertEqual([s["step"] for s in currency.MIGRATION_PLAN], list(range(1, 13)))
        for step in currency.MIGRATION_PLAN:
            self.assertEqual(set(step), {"step", "file", "function", "change", "schema"})
            self.assertTrue(step["file"].strip())
            self.assertTrue(step["function"].strip())
            self.assertTrue(step["change"].strip())
            self.assertIsInstance(step["schema"], bool)
            path = ROOT / step["file"]
            self.assertTrue(path.exists(), f"migration step names a missing file: {step['file']}")
            if step["file"].endswith(".py"):
                self.assertIn(f"def {step['function']}(", path.read_text(encoding="utf-8"),
                              f"step {step['step']} names a function that does not exist: {step['function']}")
            else:
                self.assertIn(step["function"], path.read_text(encoding="utf-8"))
        self.assertEqual([s["step"] for s in currency.MIGRATION_PLAN if s["schema"]], [1])
        text = currency.migration_plan_text()
        self.assertEqual(len(text.splitlines()), 12)
        self.assertTrue(text.startswith("1. app/db.py:_migrate_columns() (schema change): "))


@contextlib.contextmanager
def _db():
    """connect() commits on exit but never closes; close here so a reload later raises no warning."""
    conn = connect()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _reset_db() -> None:
    path = db_path()
    if path.exists():
        path.unlink()
    init_db()
    with _db() as conn:
        currency.ensure_schema(conn)
        conn.execute("DELETE FROM player WHERE id = 1")
        conn.execute(
            "INSERT INTO player (id, name, health, max_health, level, xp, gold, current_location_id) "
            "VALUES (1, 'T', 20, 20, 1, 0, 12, NULL)"
        )


def _table_counts(conn) -> dict[str, int]:
    names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")]
    counts = {}
    for name in names:
        if name == "settings":
            counts[name] = conn.execute("SELECT COUNT(*) FROM settings WHERE key != ?", (currency.CONFIG_KEY,)).fetchone()[0]
        else:
            counts[name] = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
    return counts


class CurrencyDbTests(unittest.TestCase):
    def setUp(self):
        os.environ.update(_ENV)
        _reset_db()

    def test_ensure_schema_is_a_no_op(self):
        with _db() as conn:
            before = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'index') ORDER BY name")]
            self.assertIsNone(currency.ensure_schema(conn))
            currency.ensure_schema(conn)
            after = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'index') ORDER BY name")]
        self.assertEqual(before, after)

    def test_config_row_defaults_update_and_bad_json(self):
        with _db() as conn:
            self.assertEqual(currency.get_currency_config(conn), {"set": "auto", "symbol": "", "starting_purse": None})
            clean = currency.update_currency_config(conn, {"set": "cash", "symbol": "EUR ", "unknown": 1})
            self.assertEqual(clean, {"set": "cash", "symbol": "EUR ", "starting_purse": None})
        with _db() as conn:
            self.assertEqual(currency.get_currency_config(conn), {"set": "cash", "symbol": "EUR ", "starting_purse": None})
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (currency.CONFIG_KEY,)).fetchone()
            self.assertEqual(json.loads(row["value"]), {"set": "cash", "symbol": "EUR ", "starting_purse": None})
            partial = currency.update_currency_config(conn, {"starting_purse": "500"})
            self.assertEqual(partial, {"set": "cash", "symbol": "EUR ", "starting_purse": 500})
            with self.assertRaises(ValueError):
                currency.update_currency_config(conn, {"set": "doubloons"})
            with self.assertRaises(ValueError):
                currency.update_currency_config(conn, {"starting_purse": -4})
            with self.assertRaises(ValueError):
                currency.update_currency_config(conn, {"starting_purse": "lots"})
            # A refused update leaves the row as it was.
            self.assertEqual(currency.get_currency_config(conn)["set"], "cash")
            back = currency.update_currency_config(conn, {"set": "auto", "starting_purse": None})
            self.assertEqual(back, {"set": "auto", "symbol": "EUR ", "starting_purse": None})
            conn.execute("UPDATE settings SET value = ? WHERE key = ?", ("{not json", currency.CONFIG_KEY))
            self.assertEqual(currency.get_currency_config(conn), {"set": "auto", "symbol": "", "starting_purse": None})
            conn.execute("UPDATE settings SET value = ? WHERE key = ?", (json.dumps(["a", "list"]), currency.CONFIG_KEY))
            self.assertEqual(currency.get_currency_config(conn), {"set": "auto", "symbol": "", "starting_purse": None})
            conn.execute("UPDATE settings SET value = ? WHERE key = ?", (json.dumps({"set": "doubloons"}), currency.CONFIG_KEY))
            self.assertEqual(currency.get_currency_config(conn)["set"], "auto")
            self.assertEqual(currency.active_set(conn)["id"], "coin_medieval")

    def test_active_set_auto_follows_playthrough_options(self):
        with _db() as conn:
            self.assertEqual(currency.active_set(conn)["id"], "coin_medieval")
            options = {"world_style": "space frontier salvage", "tech_level": "spacefaring salvage", "economy": "scarce"}
            conn.execute(
                "INSERT INTO settings (key, value) VALUES ('playthrough_options', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (json.dumps(options),),
            )
            picked = currency.active_set(conn)
            self.assertEqual(picked["id"], "credits")
            self.assertEqual(picked["starting_purse"], 120)
            options["economy"] = "barter-heavy"
            conn.execute("UPDATE settings SET value = ? WHERE key = 'playthrough_options'", (json.dumps(options),))
            self.assertEqual(currency.active_set(conn)["id"], "scrip")
            # An explicit choice beats detection, and the overrides apply.
            currency.update_currency_config(conn, {"set": "cash", "symbol": "EUR ", "starting_purse": 999})
            chosen = currency.active_set(conn)
            self.assertEqual(chosen["id"], "cash")
            self.assertEqual(chosen["symbol"], "EUR ")
            self.assertEqual(chosen["starting_purse"], 999)
            self.assertEqual(currency.CURRENCY_SETS["cash"]["symbol"], "$")
            conn.execute("UPDATE settings SET value = 'oops' WHERE key = 'playthrough_options'")
            currency.update_currency_config(conn, {"set": "auto"})
            self.assertEqual(currency.active_set(conn)["id"], "coin_medieval")

    def test_no_foreign_writes(self):
        with _db() as conn:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES ('playthrough_options', ?)",
                (json.dumps({"world_style": "frontier dark fantasy"}),),
            )
            before = _table_counts(conn)
            gold_before = conn.execute("SELECT gold FROM player WHERE id = 1").fetchone()[0]
            opts_before = conn.execute("SELECT value FROM settings WHERE key = 'playthrough_options'").fetchone()[0]
            currency.update_currency_config(conn, {"set": "scrip", "starting_purse": 70})
            currency.active_set(conn)
            currency.get_currency_config(conn)
            currency.update_currency_config(conn, {"set": "auto"})
            after = _table_counts(conn)
            self.assertEqual(before, after)
            self.assertEqual(conn.execute("SELECT gold FROM player WHERE id = 1").fetchone()[0], gold_before)
            self.assertEqual(conn.execute("SELECT value FROM settings WHERE key = 'playthrough_options'").fetchone()[0], opts_before)
            own = conn.execute("SELECT COUNT(*) FROM settings WHERE key = ?", (currency.CONFIG_KEY,)).fetchone()[0]
            self.assertEqual(own, 1)


class LeafTests(unittest.TestCase):
    def test_module_is_a_leaf(self):
        needle = re.compile(r"app\.currency\b|from app import currency\b|import currency\b")
        offenders = []
        for folder in ("app", "static"):
            for path in sorted((ROOT / folder).rglob("*")):
                if not path.is_file() or path.suffix not in (".py", ".js", ".html", ".css"):
                    continue
                if path == ROOT / "app" / "currency.py":
                    continue
                try:
                    text = path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
                if needle.search(text):
                    offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual(offenders, [], "the live game must not import app.currency in this pass")
        doc = currency.__doc__ or ""
        self.assertIn("Status: built, not wired (TODO n17).", doc)
        self.assertIn("Wiring (not done):", doc)
        self.assertIn("Turn on:", doc)
        self.assertIn("Tests: tests/test_currency.py", doc)

    def test_docstring_hooks_name_real_functions(self):
        doc = currency.__doc__ or ""
        hooks = re.findall(r"^\s{2}(app/[\w/]+\.py):(\w+)\(\)", doc, re.M)
        self.assertGreaterEqual(len(hooks), 8)
        for file_name, function in hooks:
            with self.subTest(hook=f"{file_name}:{function}"):
                source = (ROOT / file_name).read_text(encoding="utf-8")
                self.assertIn(f"def {function}(", source)

    def test_import_has_no_side_effects(self):
        import importlib

        module_source = (ROOT / "app" / "currency.py").read_text(encoding="utf-8")
        self.assertNotIn("print(", module_source)
        self.assertNotIn("connect()", module_source)
        self.assertNotIn("executescript", module_source)
        self.assertIs(importlib.reload(currency), sys.modules["app.currency"])


if __name__ == "__main__":
    unittest.main()
