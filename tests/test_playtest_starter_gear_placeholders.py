"""Playtest #17: game 2 started in "boots, tunic, trousers".

Those three bare names were the setup page's own fallback for the basics when
the engine did not answer. The save's start form kept only the names-only
``starter_equipment`` string (``_slim_game_start_form`` dropped the gear
cards), so restoring that character's setup rebuilt the cards from the string
and the placeholders became the next game's kit. The game-2 Start posted:

    starter_gear: [{"name": "boots", "slot": "FEET", "required": true, "keep": false,
                    "description": "", "stats": {}, ...}, tunic/TORSO, trousers/LEGS]

Now an unlocked placeholder basic with nothing else written counts as unnamed
and the engine names the slot for the world, and the start form keeps the
cards themselves.

Run:  python -m unittest tests.test_playtest_starter_gear_placeholders
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
sys.path.insert(0, str(ROOT / "tools"))

from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-gear17-"))
_ENV = {
    **isolated_data_env(str(_TMP)),
    "AI_RPG_PACK_DIR": str(_TMP / "packs"),
    "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
}
os.environ.update(_ENV)

from app import db, gear, world  # noqa: E402
from app.main import GearDefaultsRequest, api_setup_gear_defaults  # noqa: E402

PLACEHOLDERS = {"boots", "tunic", "trousers"}

# The game-2 setup (journal turn 0), trimmed to what gear reads.
GAME2 = {
    "player_name": "Miriam Shaw",
    "start_location": "Eldoria's Edge",
    "special_ability_origin": "none",
    "difficulty": "normal",
    "world_style": "frontier dark fantasy",
    "tech_level": "medieval",
    "magic_level": "rare",
    "economy": "scarce, barter-heavy",
    "player_sex": "male",
    "backstory_mode": "reincarnated",
    "starter_equipment": "boots, tunic, trousers",
}


def _card(name: str, slot: str, **extra) -> dict:
    return {
        "name": name,
        "slot": slot,
        "required": True,
        "keep": False,
        "description": "",
        "stats": {},
        "item_stats": {},
        "abilities": [],
        **extra,
    }


GAME2_CARDS = [_card("boots", "FEET"), _card("tunic", "TORSO"), _card("trousers", "LEGS")]


def setUpModule():
    os.environ.update(_ENV)
    assert str(db.db_path()).startswith(str(_TMP)), db.db_path()
    db.init_db()


def _ctx() -> dict:
    return gear.gear_context_from_setup(GAME2)


class TestPlaceholderBasicsAreUnnamed(unittest.TestCase):
    def test_the_game2_cards_get_world_names(self):
        items = gear.normalize_gear_list(GAME2_CARDS, context=_ctx(), rng=random.Random(3))
        by_slot = {it["slot"]: it for it in items if it["required"]}
        self.assertEqual(set(by_slot), {"FEET", "TORSO", "LEGS"})
        for slot, item in by_slot.items():
            self.assertNotIn(item["name"].lower(), PLACEHOLDERS, slot)
            self.assertEqual(gear.slot_for_name(item["name"]), slot, item["name"])
            self.assertTrue(item["item_stats"], item)

    def test_the_legacy_string_from_the_saved_form_gets_world_names(self):
        items = gear.normalize_gear_list(gear.gear_from_legacy_text("boots, tunic, trousers"), context=_ctx())
        names = {it["name"].lower() for it in items}
        self.assertFalse(names & PLACEHOLDERS, names)
        self.assertEqual({it["slot"] for it in items if it["required"]}, {"FEET", "TORSO", "LEGS"})

    def test_a_locked_card_keeps_its_bare_name(self):
        cards = [_card("boots", "FEET", keep=True), _card("tunic", "TORSO"), _card("trousers", "LEGS")]
        items = gear.normalize_gear_list(cards, context=_ctx())
        feet = next(it for it in items if it["slot"] == "FEET")
        self.assertEqual(feet["name"], "boots")

    def test_a_card_the_player_wrote_about_keeps_its_name(self):
        cards = [_card("boots", "FEET", description="My father's, resoled twice."), _card("tunic", "TORSO"), _card("trousers", "LEGS")]
        items = gear.normalize_gear_list(cards, context=_ctx())
        self.assertEqual(next(it for it in items if it["slot"] == "FEET")["name"], "boots")

    def test_a_real_name_is_untouched(self):
        cards = [_card("Well-Worn Boots", "FEET"), _card("Weathered Leather Tunic", "TORSO"), _card("Leather Greaves", "LEGS")]
        items = gear.normalize_gear_list(cards, context=_ctx())
        self.assertEqual([it["name"] for it in items if it["required"]], ["Well-Worn Boots", "Weathered Leather Tunic", "Leather Greaves"])

    def test_a_carried_pair_of_boots_is_not_a_basic(self):
        self.assertFalse(gear.is_placeholder_basic({"name": "boots", "slot": "CARRIED"}))

    def test_nameless_basics_from_an_offline_page_are_filled(self):
        cards = [_card("", "FEET"), _card("", "TORSO"), _card("", "LEGS")]
        items = gear.normalize_gear_list(cards, context=_ctx())
        self.assertEqual({it["slot"] for it in items if it["required"]}, {"FEET", "TORSO", "LEGS"})
        self.assertTrue(all(len(it["name"]) >= 2 for it in items))


class TestStartPaths(unittest.TestCase):
    def _rows(self):
        with db.connect() as conn:
            return [dict(r) for r in conn.execute("SELECT name, equipped_slot FROM inventory")]

    def _assert_named_basics(self):
        rows = self._rows()
        names = {r["name"].lower() for r in rows}
        self.assertFalse(names & PLACEHOLDERS, names)
        worn = {r["equipped_slot"] for r in rows if r["equipped_slot"]}
        self.assertTrue({"FEET", "TORSO", "LEGS"} <= worn, worn)

    def test_start_with_the_game2_cards(self):
        db.init_db()
        world.start_playthrough({**GAME2, "starter_gear": [dict(c) for c in GAME2_CARDS]})
        self._assert_named_basics()

    def test_start_with_only_the_saved_string(self):
        db.init_db()
        world.start_playthrough(dict(GAME2))
        self._assert_named_basics()

    def test_start_with_nothing(self):
        db.init_db()
        world.start_playthrough({k: v for k, v in GAME2.items() if k != "starter_equipment"})
        self._assert_named_basics()

    def test_gear_defaults_route_names_the_basics(self):
        out = api_setup_gear_defaults(GearDefaultsRequest(current=GAME2))["starter_gear"]
        self.assertEqual([it["slot"] for it in out], ["FEET", "TORSO", "LEGS"])
        self.assertFalse({it["name"].lower() for it in out} & PLACEHOLDERS)


class TestTheStartFormKeepsTheCards(unittest.TestCase):
    def test_slim_form_keeps_gear(self):
        cards = [_card("Well-Worn Boots", "FEET", item_stats={"weight": 0.77})]
        slim = world._slim_game_start_form({"format": "ai-rpg-setup-settings-v1", "controls": [], "gear": cards + ["junk"]})
        self.assertEqual(slim["gear"], cards)

    def test_the_form_round_trips_through_a_start(self):
        db.init_db()
        cards = [_card("Well-Worn Boots", "FEET"), _card("Weathered Leather Tunic", "TORSO"), _card("Leather Greaves", "LEGS")]
        form = {"format": "ai-rpg-setup-settings-v1", "controls": [{"name": "player_name", "value": "Miriam Shaw"}], "gear": cards}
        world.start_playthrough({**GAME2, "starter_gear": [dict(c) for c in cards], "setup_form": form})
        with db.connect() as conn:
            saved = json.loads(conn.execute("SELECT value FROM settings WHERE key = 'game_start_form'").fetchone()["value"])
        self.assertEqual([g["name"] for g in saved["gear"]], ["Well-Worn Boots", "Weathered Leather Tunic", "Leather Greaves"])


if __name__ == "__main__":
    unittest.main()
