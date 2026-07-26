"""Unit tests for energy / fatigue / mana formulas (PR1 foundation)."""
from __future__ import annotations

import unittest

from app.player_resources import (
    BASE_FATIGUE_CAP,
    action_kind_from_text,
    action_resource_delta,
    apply_ability_use,
    attr_mods,
    collapse_state,
    cooldown_status,
    default_resource_caps,
    diversify_resource_costs,
    enrich_ability_runtime,
    fatigue_stamina_mult,
    format_resource_cost,
    life_force_score,
    magic_allows_mana,
    match_ability_from_input,
    max_fatigue_for_life_force,
    normalize_resource_row,
    parse_resource_cost,
    regen_deltas,
    resource_cost_fingerprint,
    resource_settings,
    stamp_resource_cost,
    terrain_multiplier,
    travel_resource_delta,
    world_abs_minutes,
)


class TestLifeForceAndCaps(unittest.TestCase):
    def test_ordinary_fatigue_cap_is_20(self):
        self.assertEqual(max_fatigue_for_life_force(0), BASE_FATIGUE_CAP)
        self.assertEqual(max_fatigue_for_life_force(-3), BASE_FATIGUE_CAP)

    def test_life_force_raises_fatigue_cap(self):
        self.assertEqual(max_fatigue_for_life_force(5), 25)
        self.assertEqual(max_fatigue_for_life_force(100), 80)  # hard cap

    def test_life_force_from_level_and_con(self):
        low = life_force_score(level=1, max_energy=20, stats={"constitution": 10})
        high = life_force_score(level=10, max_energy=30, stats={"constitution": 18})
        self.assertGreater(high, low)
        self.assertEqual(low, 0)

    def test_magic_none_disables_mana(self):
        self.assertFalse(magic_allows_mana("none"))
        self.assertFalse(magic_allows_mana("no magic"))
        self.assertTrue(magic_allows_mana("rare"))
        caps = default_resource_caps({"magic_level": "none"}, player={"level": 1})
        self.assertEqual(caps["max_mana"], 0)
        caps_m = default_resource_caps({"magic_level": "common"}, player={"level": 1})
        self.assertGreater(caps_m["max_mana"], 0)


class TestFatigueMultAndTravel(unittest.TestCase):
    def test_fatigue_raises_stamina_cost(self):
        fresh = fatigue_stamina_mult(0, 20)
        tired = fatigue_stamina_mult(20, 20)
        self.assertAlmostEqual(fresh, 1.0)
        self.assertGreater(tired, fresh)
        self.assertAlmostEqual(tired, 1.75)

    def test_terrain_road_cheaper_than_mountain(self):
        self.assertLess(terrain_multiplier("road"), terrain_multiplier("mountain trail"))
        self.assertEqual(terrain_multiplier("plains"), 1.0)

    def test_travel_costs_energy_and_fatigue(self):
        road = travel_resource_delta(terrain="road", minutes=60, load_ratio=0.4, fatigue=0)
        forest = travel_resource_delta(terrain="forest", minutes=60, load_ratio=0.4, fatigue=0)
        self.assertGreater(road["energy"], 0)
        self.assertGreater(forest["energy"], road["energy"])
        self.assertGreaterEqual(forest["fatigue"], road["fatigue"])

    def test_high_fatigue_multiplies_travel_energy(self):
        light = travel_resource_delta(terrain="plains", minutes=30, fatigue=0, max_fatigue=20)
        heavy = travel_resource_delta(terrain="plains", minutes=30, fatigue=20, max_fatigue=20)
        self.assertGreaterEqual(heavy["energy"], light["energy"])

    def test_con_reduces_travel_drain(self):
        weak = travel_resource_delta(
            terrain="hills", minutes=40, fatigue=0, stats={"constitution": 8, "strength": 10, "dexterity": 10}
        )
        strong = travel_resource_delta(
            terrain="hills", minutes=40, fatigue=0, stats={"constitution": 18, "strength": 10, "dexterity": 10}
        )
        self.assertLessEqual(strong["energy"], weak["energy"])
        self.assertLessEqual(strong["fatigue"], weak["fatigue"])


class TestRegen(unittest.TestCase):
    def test_sleep_recovers_more_than_wait(self):
        wait = regen_deltas(minutes=60, kind="wait", max_energy=20, max_mana=10, max_fatigue=20, energy=0, mana=0, fatigue=15)
        sleep = regen_deltas(minutes=60, kind="sleep", max_energy=20, max_mana=10, max_fatigue=20, energy=0, mana=0, fatigue=15)
        med = regen_deltas(minutes=60, kind="meditate", max_energy=20, max_mana=10, max_fatigue=20, energy=0, mana=0, fatigue=15)
        self.assertGreater(sleep["energy"], wait["energy"])
        self.assertGreater(med["mana"], wait["mana"])
        self.assertGreater(sleep["fatigue"], wait["fatigue"])

    def test_long_sleep_clears_most_pools(self):
        d = regen_deltas(
            minutes=480,
            kind="sleep",
            max_energy=20,
            max_mana=12,
            max_fatigue=20,
            energy=0,
            mana=0,
            fatigue=18,
        )
        self.assertGreaterEqual(d["energy"], 15)
        self.assertGreaterEqual(d["fatigue"], 10)

    def test_no_mana_regen_when_max_zero(self):
        d = regen_deltas(minutes=120, kind="meditate", max_energy=20, max_mana=0, energy=5, mana=0, fatigue=5)
        self.assertEqual(d["mana"], 0)

    def test_regen_does_not_overshoot(self):
        d = regen_deltas(minutes=9999, kind="sleep", max_energy=20, max_mana=10, energy=18, mana=9, fatigue=2)
        self.assertLessEqual(d["energy"], 2)
        self.assertLessEqual(d["mana"], 1)
        self.assertLessEqual(d["fatigue"], 2)


class TestNormalizeAndStamp(unittest.TestCase):
    def test_normalize_clamps_and_bands(self):
        row = normalize_resource_row(
            {"energy": 99, "max_energy": 20, "mana": -1, "max_mana": 10, "fatigue": 15, "max_fatigue": 20, "level": 1},
            {"magic_level": "rare"},
        )
        self.assertEqual(row["energy"], 20)
        self.assertEqual(row["mana"], 0)
        # 15/20 = 0.75 → heavy (>= 0.75)
        self.assertEqual(row["band"], "heavy")

    def test_attr_mods_aliases(self):
        mods = attr_mods({"con": 14, "str": 12, "dex": 8})
        self.assertAlmostEqual(mods["con_mod"], 0.4)
        self.assertAlmostEqual(mods["str_mod"], 0.2)
        self.assertAlmostEqual(mods["dex_mod"], -0.2)

    def test_stamp_mild_power_no_week_cooldown(self):
        mild = stamp_resource_cost(
            {"name": "Candle Light", "description": "A mild glow spell", "power_type": "active"},
            magic_ok=True,
        )
        cost = mild.get("resource_cost") or {}
        # Tier estimation may vary; never allow week-long CD for candle-like mild
        self.assertLess(int(cost.get("cooldown_minutes") or 0), 7 * 24 * 60)
        if cost.get("cooldown_minutes", 0) and "mild" in str(mild).lower():
            self.assertLessEqual(cost["cooldown_minutes"], 60)

    def test_stamp_passive_zero_cost(self):
        p = stamp_resource_cost({"name": "Hardy", "description": "Always on", "power_type": "passive"})
        c = p["resource_cost"]
        self.assertEqual(c["energy"], 0)
        self.assertEqual(c["mana"], 0)
        self.assertEqual(c["cooldown_minutes"], 0)

    def test_format_and_parse_cost(self):
        c = parse_resource_cost({"energy": 3, "mana": 2, "cooldown_minutes": 60, "debuffs": ["drained"]})
        text = format_resource_cost(c)
        self.assertIn("3 energy", text)
        self.assertIn("2 mana", text)
        self.assertIn("1h cooldown", text)
        self.assertIn("drained", text)

    def test_stamp_fills_empty_cost_text(self):
        ab = stamp_resource_cost(
            {"name": "Arcane Bolt", "description": "A magic spell that blasts", "cost": ""},
            magic_ok=True,
        )
        self.assertTrue(ab.get("cost"))
        self.assertGreater(ab["resource_cost"]["mana"], 0)


class TestAbilityUseAndCooldown(unittest.TestCase):
    def test_match_longest_ability_name(self):
        abilities = [
            {"name": "Flame", "locked": False},
            {"name": "Flame Veil", "locked": False},
        ]
        m = match_ability_from_input("I activate Flame Veil at the guard", abilities)
        self.assertIsNotNone(m)
        self.assertEqual(m["name"], "Flame Veil")

    def test_match_none_when_not_mentioned(self):
        self.assertIsNone(match_ability_from_input("I walk to the market", [{"name": "Flame Veil"}]))

    def test_cooldown_status_remaining(self):
        ab = {"id": 3, "name": "Bolt"}
        now = {"day": 1, "minute": 100}
        cds = {"id:3": {"ready_at_abs": world_abs_minutes(now) + 45}}
        st = cooldown_status(ab, cds, world_time=now)
        self.assertFalse(st["ready"])
        self.assertEqual(st["remaining_minutes"], 45)
        later = {"day": 1, "minute": 200}
        st2 = cooldown_status(ab, cds, world_time=later)
        self.assertTrue(st2["ready"])

    def test_enrich_blocks_locked(self):
        ab = enrich_ability_runtime(
            {"name": "Secret Art", "description": "strong power", "locked": True},
            magic_ok=True,
            resources={"energy": 20, "mana": 20, "health": 20},
            world_time={"day": 1, "minute": 0},
        )
        self.assertFalse(ab["can_use"])
        self.assertIn("locked", ab["block_reasons"])

    def test_apply_ability_use_spends_and_cools(self):
        import sqlite3

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(
            """
            CREATE TABLE player (
              id INTEGER PRIMARY KEY CHECK (id = 1),
              health INTEGER, max_health INTEGER, level INTEGER,
              energy INTEGER, max_energy INTEGER,
              mana INTEGER, max_mana INTEGER,
              fatigue INTEGER, max_fatigue INTEGER
            );
            CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT);
            INSERT INTO player VALUES (1, 20, 20, 1, 20, 20, 15, 15, 0, 20);
            """
        )
        store: dict = {}

        def sget():
            return dict(store)

        def sset(k, v):
            store[k] = v

        ability = {
            "id": 1,
            "name": "Arcane Pulse",
            "description": "A moderate magic spell",
            "locked": False,
            "resource_cost": {"energy": 1, "mana": 4, "fatigue": 1, "health": 0, "cooldown_minutes": 30, "debuffs": []},
        }
        result = apply_ability_use(
            conn,
            ability,
            options={"magic_level": "common"},
            world_time={"day": 1, "minute": 60},
            turn=2,
            hard_block=True,
            settings_get=sget,
            settings_set=sset,
        )
        self.assertTrue(result["ok"])
        self.assertFalse(result["blocked"])
        row = conn.execute("SELECT energy, mana, fatigue FROM player WHERE id = 1").fetchone()
        self.assertEqual(row["energy"], 19)
        self.assertEqual(row["mana"], 11)
        self.assertEqual(row["fatigue"], 1)
        self.assertIn("ability_cooldowns", store)
        # Second use should block on cooldown
        result2 = apply_ability_use(
            conn,
            ability,
            options={"magic_level": "common"},
            world_time={"day": 1, "minute": 70},
            turn=3,
            hard_block=True,
            settings_get=sget,
            settings_set=sset,
        )
        self.assertTrue(result2["blocked"])
        self.assertIn("cooldown", result2["reasons"])

    def test_apply_blocks_insufficient_mana(self):
        import sqlite3

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(
            """
            CREATE TABLE player (
              id INTEGER PRIMARY KEY CHECK (id = 1),
              health INTEGER, max_health INTEGER, level INTEGER,
              energy INTEGER, max_energy INTEGER,
              mana INTEGER, max_mana INTEGER,
              fatigue INTEGER, max_fatigue INTEGER
            );
            CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT);
            INSERT INTO player VALUES (1, 20, 20, 1, 20, 20, 1, 15, 0, 20);
            """
        )
        store: dict = {}
        ability = {
            "id": 2,
            "name": "Big Spell",
            "description": "magic blast",
            "resource_cost": {"mana": 8, "energy": 0, "fatigue": 0, "health": 0, "cooldown_minutes": 0, "debuffs": []},
        }
        result = apply_ability_use(
            conn,
            ability,
            options={"magic_level": "high"},
            world_time={"day": 1, "minute": 0},
            hard_block=True,
            settings_get=lambda: store,
            settings_set=lambda k, v: store.__setitem__(k, v),
        )
        self.assertTrue(result["blocked"])
        self.assertIn("insufficient_mana", result["reasons"])
        row = conn.execute("SELECT mana FROM player WHERE id = 1").fetchone()
        self.assertEqual(row["mana"], 1)  # unchanged


class TestDiversifyAndCollapse(unittest.TestCase):
    def test_diversify_makes_distinct_shapes(self):
        abilities = [
            {"name": "A", "description": "A mild glow spell for light", "cost": "1 mana"},
            {"name": "B", "description": "A mild glow spell for light", "cost": "1 mana"},
            {"name": "C", "description": "A mild glow spell for light", "cost": "1 mana"},
        ]
        out = diversify_resource_costs(abilities, magic_ok=True, force=True)
        fps = [resource_cost_fingerprint(a.get("resource_cost")) for a in out]
        self.assertEqual(len(fps), len(set(fps)), f"expected unique shapes, got {fps}")

    def test_collapse_at_zero_energy(self):
        col = collapse_state({"energy": 0, "max_energy": 20, "fatigue": 5, "max_fatigue": 20})
        self.assertTrue(col["blocks_physical"])
        self.assertTrue(col["needs_rest"])
        self.assertIn("zero_energy", col["effects"])

    def test_collapse_at_full_fatigue(self):
        col = collapse_state({"energy": 10, "max_energy": 20, "fatigue": 20, "max_fatigue": 20})
        self.assertGreaterEqual(col["action_cost_mult"], 1.5)
        self.assertIn("full_fatigue", col["effects"])

    def test_action_kind_and_delta(self):
        self.assertEqual(action_kind_from_text("I attack the bandit"), "combat")
        self.assertEqual(action_kind_from_text("I ask about the road"), "talk")
        combat = action_resource_delta(kind="combat", minutes=8, fatigue=0)
        talk = action_resource_delta(kind="talk", minutes=5, fatigue=0)
        self.assertGreater(combat["energy"], talk["energy"])

    def test_resource_settings_merge(self):
        cfg = resource_settings({"resource_settings": {"drain_scale": 2.0, "travel_hard_block": False}})
        self.assertEqual(cfg["drain_scale"], 2.0)
        self.assertFalse(cfg["travel_hard_block"])
        self.assertTrue(cfg["action_energy_enabled"])

    def test_travel_hard_block_no_spend(self):
        import sqlite3

        from app.player_resources import apply_travel_spend

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(
            """
            CREATE TABLE player (
              id INTEGER PRIMARY KEY CHECK (id = 1),
              health INTEGER, max_health INTEGER, level INTEGER,
              energy INTEGER, max_energy INTEGER,
              mana INTEGER, max_mana INTEGER,
              fatigue INTEGER, max_fatigue INTEGER
            );
            INSERT INTO player VALUES (1, 20, 20, 1, 1, 20, 0, 0, 0, 20);
            """
        )
        result = apply_travel_spend(
            conn,
            terrain="mountain",
            minutes=60,
            load_ratio=0.5,
            options={"resource_settings": {"travel_hard_block": True}},
            hard_block=True,
        )
        self.assertTrue(result.get("blocked"))
        row = conn.execute("SELECT energy FROM player WHERE id = 1").fetchone()
        self.assertEqual(row["energy"], 1)


if __name__ == "__main__":
    unittest.main()
