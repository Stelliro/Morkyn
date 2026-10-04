"""Starting gear is a structured kit, and the engine owns its numbers.

The setup form used to post one comma string ("travel-worn cloak, empty leather
pouch, ...") and the gear card's slot, effect and rules boxes stayed empty, so
no starting item ever carried a stat bonus, a slot or an ability into play.

Now ``starter_gear`` is a list of items (name, slot, description, stat bonuses,
item stats, abilities). ``app.gear`` validates it and rolls whatever the model
left blank; ``start_playthrough`` writes every field into the inventory table;
``get_state`` folds the bonuses into ``player.effective_stats``. Three worn
basics (feet, torso, legs) always exist, and LEGS is a real body slot.

Run:  python -m unittest tests.test_starter_gear_engine
"""
from __future__ import annotations

import json
import os
import random
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-gear-test-"))
_ENV = {
    "AI_RPG_DB": str(_TMP / "world.db"),
    "AI_RPG_PACK_DIR": str(_TMP / "packs"),
    "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
    "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
    "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
    "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
}
os.environ.update(_ENV)

from fastapi import HTTPException  # noqa: E402

from app import db, gear, world  # noqa: E402
from app.main import (  # noqa: E402
    GearDefaultsRequest,
    GearStatsRequest,
    SetupRequest,
    api_setup_gear_defaults,
    api_setup_gear_stats,
)


def setUpModule():
    os.environ.update(_ENV)
    assert str(db.db_path()).startswith(str(_TMP)), db.db_path()
    db.init_db()


MEDIEVAL = {"world_style": "frontier dark fantasy", "tech_level": "medieval", "economy": "scarce", "difficulty": "hard"}
# An easy start (cap 4) so the trousers' own +1 survives whatever the basics roll.
EASY = {**MEDIEVAL, "difficulty": "easy"}

KIT = [
    {"name": "travel-worn cloak", "slot": "back", "description": "Oiled wool, hem gone to threads."},
    {"name": "empty leather pouch", "slot": "waist"},
    {"name": "small glass vial"},
    {"name": "iron farming tool"},
    {"name": "rough loaf of bread"},
    {
        "name": "patched trousers",
        "slot": "LEGS",
        "stats": {"dexterity": 1},
        "item_stats": {"weight": 0.6, "durability": 44, "protection": 0, "value": 3, "rarity": "common"},
        "abilities": [
            {
                "name": "Quiet Hem",
                "description": "Once per scene, the wearer moves without a sound for a breath.",
                "cost": "A thread tears each time.",
                "growth_math": "item-bound; F->E@90; +1 stealth per rank while worn",
                "power_type": "item_bound",
            }
        ],
    },
]


def _rows() -> list[dict]:
    with db.connect() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM inventory ORDER BY id").fetchall()]


class TestTheKitIsNormalized(unittest.TestCase):
    def test_the_three_basics_are_always_there(self):
        items = gear.normalize_gear_list([], context=gear.gear_context_from_setup(MEDIEVAL), rng=random.Random(1))
        self.assertEqual([it["slot"] for it in items], ["FEET", "TORSO", "LEGS"])
        self.assertTrue(all(it["required"] for it in items))
        for it in items:
            self.assertTrue(it["name"])
            self.assertEqual(set(it["item_stats"]), set(gear.ITEM_STAT_KEYS))

    def test_a_kit_without_a_torso_gets_one_and_keeps_the_rest(self):
        ctx = gear.gear_context_from_setup(MEDIEVAL)
        items = gear.normalize_gear_list(KIT, context=ctx, rng=random.Random(3))
        names = [it["name"] for it in items]
        self.assertIn("patched trousers", names)
        self.assertIn("travel-worn cloak", names)
        required = {it["slot"]: it for it in items if it["required"]}
        self.assertEqual(set(required), {"FEET", "TORSO", "LEGS"})
        self.assertEqual(required["LEGS"]["name"], "patched trousers")
        self.assertEqual(next(it for it in items if it["name"] == "travel-worn cloak")["slot"], "BACK")

    def test_the_bonus_total_is_capped_by_start_power(self):
        ctx = gear.gear_context_from_setup(MEDIEVAL)  # hard -> weak -> cap 1
        greedy = KIT + [{"name": "iron ring", "stats": {"might": 5, "wisdom": 2}}]
        items = gear.normalize_gear_list(greedy, context=ctx, rng=random.Random(5))
        total = sum(v for it in items for v in it["stats"].values() if v > 0)
        self.assertLessEqual(total, gear.START_BONUS_TOTAL_CAP["weak"])
        strong = gear.gear_context_from_setup({**MEDIEVAL, "difficulty": "easy"})
        self.assertEqual(strong["start_power"], "strong")
        self.assertGreater(gear.START_BONUS_TOTAL_CAP["strong"], gear.START_BONUS_TOTAL_CAP["weak"])

    def test_the_model_bonus_is_clamped_per_item_and_mapped_to_a_canonical_key(self):
        self.assertEqual(gear.normalize_stat_bonuses({"might": 5}), {"strength": gear.PER_ITEM_BONUS_MAX})
        self.assertEqual(gear.normalize_stat_bonuses("+1 dex"), {"dexterity": 1})
        self.assertEqual(gear.normalize_stat_bonuses({"luck": 2}), {})

    def test_slots_come_from_the_name_when_the_model_leaves_them_blank(self):
        self.assertEqual(gear.slot_for_name("patched trousers"), "LEGS")
        self.assertEqual(gear.slot_for_name("travel-worn cloak"), "BACK")
        self.assertEqual(gear.slot_for_name("leather boots"), "FEET")
        self.assertEqual(gear.slot_for_name("rough loaf of bread"), gear.CARRIED)
        self.assertEqual(gear.normalize_slot("legs/feet"), gear.CARRIED)
        self.assertEqual(gear.normalize_slot("Torso"), "TORSO")

    def test_rolls_are_deterministic_for_a_seed(self):
        ctx = gear.gear_context_from_setup(MEDIEVAL)
        a = gear.normalize_gear_list(KIT, context=ctx, rng=random.Random(11))
        b = gear.normalize_gear_list(KIT, context=ctx, rng=random.Random(11))
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))

    def test_the_legacy_string_still_parses(self):
        items = gear.gear_from_legacy_text("worn coat (torso) [stat] — +1 endurance; coiled rope, 3-day rations")
        self.assertEqual([it["name"] for it in items], ["worn coat", "coiled rope", "3-day rations"])


class TestLegsIsABodySlot(unittest.TestCase):
    def test_legs_sits_between_waist_and_feet(self):
        codes = [row[0] for row in world.DEFAULT_EQUIPMENT_SLOTS]
        self.assertIn("LEGS", codes)
        self.assertLess(codes.index("WAIST"), codes.index("LEGS"))
        self.assertLess(codes.index("LEGS"), codes.index("FEET"))

    def test_the_world_slot_mapper_knows_legs(self):
        self.assertEqual(world._default_equip_slot_for_item("wool trousers"), "LEGS")
        self.assertEqual(world._default_equip_slot_for_item("dusty boots"), "FEET")
        self.assertEqual(world._default_equip_slot_for_item("loaf of bread"), "")


class TestStartWritesTheKit(unittest.TestCase):
    def setUp(self):
        db.init_db()
        world.start_playthrough(
            {
                "player_name": "Ash",
                "start_location": "Low Gate",
                "special_ability_origin": "none",
                **EASY,
                "starter_gear": KIT,
            }
        )

    def test_every_field_lands_in_sqlite(self):
        rows = _rows()
        by_name = {r["name"]: r for r in rows}
        self.assertIn("patched trousers", by_name)
        trousers = by_name["patched trousers"]
        self.assertEqual(trousers["equipped_slot"], "LEGS")
        self.assertEqual(trousers["item_type"], "clothing")
        self.assertEqual(json.loads(trousers["stat_modifiers"]), {"dexterity": 1})
        self.assertEqual(json.loads(trousers["stat_links"]), {"dexterity": 1})
        granted = json.loads(trousers["granted_abilities"])
        self.assertEqual(granted[0]["name"], "Quiet Hem")
        self.assertIn("F->E@90", granted[0]["growth_math"])
        self.assertEqual(granted[0]["power_type"], "item_bound")
        item_stats = json.loads(trousers["item_stats"])
        self.assertEqual(item_stats["durability"], 44)
        self.assertEqual(item_stats["rarity"], "common")
        self.assertAlmostEqual(trousers["weight"], 0.6)
        self.assertIn("Starting gear", trousers["description"])  # no description given: the engine line
        self.assertIn("Oiled wool", by_name["travel-worn cloak"]["description"])

    def test_the_three_basics_are_worn(self):
        worn = {r["equipped_slot"] for r in _rows() if r["equipped_slot"]}
        self.assertTrue({"FEET", "TORSO", "LEGS"} <= worn, worn)
        for slot in ("FEET", "TORSO", "LEGS"):
            self.assertEqual(sum(1 for r in _rows() if r["equipped_slot"] == slot), 1, slot)

    def test_the_bonus_reaches_effective_stats_and_the_ability_reaches_play(self):
        state = world.get_state()
        # The trousers' own +1 is there; another basic may have rolled its own +1 on top.
        self.assertGreaterEqual(float(state["player"]["effective_stats"].get("dexterity") or 0), 1)
        self.assertIn("Quiet Hem", state["player"]["equipment_ability_names"])
        trousers = next(i for i in state["inventory"] if i["name"] == "patched trousers")
        self.assertEqual(trousers["item_stats"]["durability"], 44)
        granted = trousers["granted_abilities"][0]
        self.assertEqual(granted["power_type"], "item_bound")
        self.assertIn("F->E@90", granted["growth_math"])

    def test_the_settings_remember_the_kit_and_the_names(self):
        options = world.get_state()["settings"]["playthrough_options"]
        self.assertEqual([g["slot"] for g in options["starter_gear"] if g["required"]], ["FEET", "TORSO", "LEGS"])
        self.assertIn("patched trousers", options["starter_equipment"])
        self.assertIn("travel-worn cloak", options["starter_equipment"])


class TestTheEngineLineWhenNoDescription(unittest.TestCase):
    def test_a_blank_description_gets_the_provenance_line(self):
        db.init_db()
        world.start_playthrough(
            {"player_name": "Ash", "start_location": "Low Gate", "special_ability_origin": "none", **MEDIEVAL, "starter_gear": [{"name": "tin cup"}]}
        )
        cup = next(r for r in _rows() if r["name"] == "tin cup")
        self.assertIn("Starting gear", cup["description"])


class TestTheLegacyStringStillSeeds(unittest.TestCase):
    def test_the_comma_string_alone_seeds_items_and_the_basics(self):
        db.init_db()
        world.start_playthrough(
            {
                "player_name": "Ash",
                "start_location": "Low Gate",
                "special_ability_origin": "none",
                **MEDIEVAL,
                "starter_equipment": "coiled rope, tin cup, dusty boots",
            }
        )
        rows = _rows()
        names = {r["name"] for r in rows}
        self.assertIn("coiled rope", names)
        self.assertIn("tin cup", names)
        worn = {r["equipped_slot"] for r in rows if r["equipped_slot"]}
        self.assertTrue({"FEET", "TORSO", "LEGS"} <= worn, worn)
        self.assertEqual(next(r for r in rows if r["equipped_slot"] == "FEET")["name"], "dusty boots")


class TestTheSetupModel(unittest.TestCase):
    def test_the_kit_is_accepted_and_the_names_are_derived(self):
        request = SetupRequest(player_name="Ash", starter_gear=KIT)
        self.assertEqual(len(request.starter_gear), len(KIT))
        self.assertEqual(request.starter_gear[-1].abilities[0].power_type, "item_bound")
        self.assertIn("patched trousers", request.starter_equipment)
        self.assertIn("travel-worn cloak", request.starter_equipment)

    def test_a_blank_kit_is_a_list(self):
        self.assertEqual(SetupRequest(player_name="Ash", starter_gear=None).starter_gear, [])


class TestTheEngineRoutes(unittest.TestCase):
    def test_gear_defaults_returns_the_basics_for_this_world(self):
        payload = api_setup_gear_defaults(GearDefaultsRequest(current={"tech_level": "modern", "world_style": "urban isekai"}))
        items = payload["starter_gear"]
        self.assertEqual([it["slot"] for it in items], ["FEET", "TORSO", "LEGS"])
        self.assertTrue(all(it["required"] for it in items))

    def test_gear_stats_rolls_the_numbers_and_keeps_the_card(self):
        payload = api_setup_gear_stats(
            GearStatsRequest(
                item={"name": "oiled leather boots", "slot": "FEET", "required": True, "keep": True, "description": "Good soles.", "abilities": [{"name": "Sure Step"}]},
                current=MEDIEVAL,
            )
        )
        item = payload["item"]
        self.assertEqual(item["slot"], "FEET")
        self.assertTrue(item["required"] and item["keep"])
        self.assertEqual(item["description"], "Good soles.")
        self.assertEqual(item["abilities"][0]["name"], "Sure Step")
        self.assertEqual(set(item["item_stats"]), set(gear.ITEM_STAT_KEYS))
        self.assertEqual(item["item_stats"]["protection"], 1)

    def test_gear_stats_refuses_a_nameless_item(self):
        with self.assertRaises(HTTPException):
            api_setup_gear_stats(GearStatsRequest(item={"name": ""}, current={}))


if __name__ == "__main__":
    unittest.main()
