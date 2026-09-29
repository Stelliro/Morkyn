"""Playtest 2026-09-23: unequip must clear the worn slot, and xAI chat must not 404.

The shoes line was "i go to take off my non-slip shoes". Narration quoted it and
Feet stayed worn, because neither the DSL draft nor the fallback emits
equipment_changes. The chat call posted to {base}/v1/chat/completions while the
preset base is already https://api.x.ai/v1, so xAI returned the URL 404.

Run: python -m unittest tests.test_playtest_unequip_and_chat_url
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-unequip-test-"))
os.environ.update(
    {
        "AI_RPG_DB": str(_TMP / "world.db"),
        "AI_RPG_PACK_DIR": str(_TMP / "packs"),
        "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
        "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
        "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
        "AI_RPG_CAMPAIGN_SLOTS": str(_TMP / "slots"),
        "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
    }
)

from app.db import connect, init_db  # noqa: E402
from app.llm import _join_openai_v1, fallback_turn  # noqa: E402
from app.world import (  # noqa: E402
    _apply_equipment_changes,
    resolve_worn_unequip,
    worn_unequip_targets,
)

init_db()

SHOES = "i go to take off my non-slip shoes"
INVENTORY = [
    {"code": "I1", "name": "kitchen apron", "quantity": 1, "equipped_slot": "TORSO"},
    {"code": "I2", "name": "non-slip shoes", "quantity": 1, "equipped_slot": "FEET"},
]


def _seed_shoes() -> None:
    with connect() as conn:
        conn.execute("DELETE FROM inventory")
        conn.execute(
            "INSERT INTO inventory (code, name, quantity, description, equipped_slot) VALUES (?, ?, ?, ?, ?)",
            ("I2", "non-slip shoes", 1, "kitchen shoes", "FEET"),
        )
        conn.execute(
            """
            INSERT INTO equipment_slots (code, name, category, capacity, accepts, sort_order)
            VALUES ('FEET', 'Feet', 'feet', 1, '["boots", "shoes", "greaves"]', 110)
            ON CONFLICT(code) DO UPDATE SET accepts = excluded.accepts
            """
        )


class ChatUrlTests(unittest.TestCase):
    def test_preset_base_is_not_doubled(self):
        self.assertEqual(
            _join_openai_v1("https://api.x.ai/v1", "/v1/chat/completions"),
            "https://api.x.ai/v1/chat/completions",
        )

    def test_host_without_v1_still_gets_one(self):
        self.assertEqual(
            _join_openai_v1("https://api.x.ai", "/chat/completions"),
            "https://api.x.ai/v1/chat/completions",
        )
        self.assertEqual(
            _join_openai_v1("http://localhost:8080", "/v1/chat/completions"),
            "http://localhost:8080/v1/chat/completions",
        )

    def test_models_probe_uses_the_same_root(self):
        self.assertEqual(_join_openai_v1("https://api.x.ai/v1", "/models"), "https://api.x.ai/v1/models")


class UnequipTests(unittest.TestCase):
    def test_the_playtest_line_selects_the_worn_shoes(self):
        targets = worn_unequip_targets(INVENTORY, [], SHOES)
        self.assertEqual([item["code"] for item in targets], ["I2"])

    def test_looking_at_the_shoes_does_not_remove_them(self):
        self.assertEqual(worn_unequip_targets(INVENTORY, [], "i look at my non-slip shoes"), [])

    def test_a_negated_unequip_does_not_remove_them(self):
        self.assertEqual(worn_unequip_targets(INVENTORY, [], "i don't take off my non-slip shoes"), [])

    def test_shoes_without_the_full_name_still_clears_feet(self):
        targets = worn_unequip_targets(INVENTORY, [], "i take my shoes off")
        self.assertEqual([item["code"] for item in targets], ["I2"])

    def test_apply_clears_the_worn_slot_the_panel_reads(self):
        _seed_shoes()
        with connect() as conn:
            result: dict = {"narration": "The street is quiet.", "equipment_changes": []}
            report = resolve_worn_unequip(conn, result, SHOES)
            _apply_equipment_changes(conn, result["equipment_changes"])
            slot = conn.execute("SELECT equipped_slot FROM inventory WHERE code = 'I2'").fetchone()["equipped_slot"]
        self.assertEqual(report["status"], "unequipped")
        self.assertEqual(report["items"], ["non-slip shoes"])
        self.assertEqual(slot, "")
        self.assertTrue(any(change.get("equip") is False for change in result["equipment_changes"]))


class FallbackHonestyTests(unittest.TestCase):
    def test_shoe_fallback_says_they_are_not_worn_and_does_not_quote_a_success(self):
        narration = fallback_turn(
            {"current_location": {"name": "Low Gate Timber Arch"}, "inventory": INVENTORY},
            SHOES,
        )["narration"]
        self.assertIn("not worn", narration)
        self.assertIn("non-slip shoes", narration)
        self.assertNotIn("Your intent was clear", narration)
        self.assertNotIn("If you press forward", narration)

    def test_unresolved_action_is_not_narrated_as_done(self):
        narration = fallback_turn(
            {"current_location": {"name": "Low Gate Timber Arch"}, "inventory": INVENTORY},
            "i wave at the birds",
        )["narration"]
        self.assertIn("was not carried out", narration)
        self.assertNotIn("i wave at the birds", narration.lower())

    def test_combat_fallback_states_the_server_roll_instead_of_a_canned_success(self):
        narration = fallback_turn(
            {
                "current_location": {"name": "Low Gate Timber Arch"},
                "inventory": INVENTORY,
                "mechanics_context": {
                    "combat": {
                        "status": "resolved_player_attack",
                        "player_attack": {"weapon": "unarmed"},
                        "target": {"code": "A", "name": "Grainpost"},
                        "resolution": {
                            "outcome": "hit",
                            "damage": 3,
                            "target_health_before": 21,
                            "target_health_after": 18,
                        },
                    }
                },
            },
            "i go and punch the closest person to me",
        )["narration"]
        self.assertIn("server roll", narration)
        self.assertIn("Grainpost", narration)
        self.assertIn("3", narration)
        self.assertNotIn("Your intent was clear", narration)
        self.assertNotIn("If you press forward", narration)


if __name__ == "__main__":
    unittest.main()
