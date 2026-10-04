"""Campaign-scoped tables start empty and ride along in a save.

`quest_clocks` (NPC/notice offer clocks) and `name_ledger` (names the world
committed to) are per campaign. Neither was deleted by `_clear_playthrough`
nor listed in `WORLD_TABLES`, so a new playthrough inherited the previous
campaign's clocks and names while a saved slot silently dropped both.

Run:  python -m unittest tests.test_playthrough_tables
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-playthrough-tables-test-"))
_ENV = {
    "AI_RPG_DB": str(_TMP / "world.db"),
    "AI_RPG_PACK_DIR": str(_TMP / "packs"),
    "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
    "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
    "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
    "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
    "AI_RPG_CAMPAIGN_SLOTS": str(_TMP / "slots"),
}
os.environ.update(_ENV)

from app import db, local_intel, world  # noqa: E402
from app.naming import ledger_lookup, ledger_record  # noqa: E402


def setUpModule():
    os.environ.update(_ENV)
    assert str(db.db_path()).startswith(str(_TMP)), db.db_path()
    db.init_db()


def _start():
    world.start_playthrough({"player_name": "Ash", "start_location": "Low Gate", "special_ability_origin": "none"})


def _seed_campaign_state():
    with db.connect() as conn:
        local_intel.ensure_quest_clock_table(conn)
        conn.execute(
            "INSERT OR REPLACE INTO quest_clocks (subject_key, offers, chance, phase, phase_day, quest_id, last_day) "
            "VALUES ('npc:7', 1, 5, 'offered', 40, 123, 40)"
        )
        ledger_record(conn, "letter", "Someone Named", source="minted", turn=3)


def _clock_rows():
    with db.connect() as conn:
        return [tuple(r) for r in conn.execute("SELECT subject_key, last_day FROM quest_clocks").fetchall()]


class TestNewPlaythroughStartsClean(unittest.TestCase):
    def test_clocks_and_ledger_are_cleared(self):
        db.init_db()
        _start()
        _seed_campaign_state()
        self.assertEqual(_clock_rows(), [("npc:7", 40)])
        _start()  # the public entry point for a new campaign
        self.assertEqual(_clock_rows(), [])
        with db.connect() as conn:
            self.assertEqual(ledger_lookup(conn, "letter"), "")

    def test_reused_npc_id_rolls_its_own_clock(self):
        db.init_db()
        _start()
        _seed_campaign_state()
        _start()
        with db.connect() as conn:
            local_intel.ensure_npc_clock(conn, 7, role="smith")
            row = conn.execute("SELECT last_day, quest_id FROM quest_clocks WHERE subject_key = 'npc:7'").fetchone()
        self.assertIsNotNone(row)
        self.assertNotEqual((int(row["last_day"]), int(row["quest_id"])), (40, 123), "the old campaign's clock must not be served")

    def test_tables_are_in_every_allowlist(self):
        for table in ("quest_clocks", "name_ledger"):
            self.assertIn(table, world.WORLD_TABLES)
            self.assertIn(table, world.RESTORE_ORDER)
            self.assertIn(table, world._REPLACE_ONLY_WHEN_EXPORTED)


class TestSaveCarriesCampaignTables(unittest.TestCase):
    def test_export_clear_import_round_trip(self):
        db.init_db()
        _start()
        _seed_campaign_state()
        payload = json.loads(json.dumps(world.export_world()))
        self.assertEqual(len(payload["tables"].get("quest_clocks") or []), 1)
        self.assertEqual(len(payload["tables"].get("name_ledger") or []), 1)
        _start()
        self.assertEqual(_clock_rows(), [])
        world.import_world(payload)
        self.assertEqual(_clock_rows(), [("npc:7", 40)])
        with db.connect() as conn:
            self.assertEqual(ledger_lookup(conn, "letter"), "Someone Named")

    def test_old_slot_without_the_tables_keeps_the_live_rows(self):
        db.init_db()
        _start()
        _seed_campaign_state()
        payload = json.loads(json.dumps(world.export_world()))
        payload["tables"].pop("quest_clocks", None)
        payload["tables"].pop("name_ledger", None)
        world.import_world(payload)
        self.assertEqual(_clock_rows(), [("npc:7", 40)])
        with db.connect() as conn:
            self.assertEqual(ledger_lookup(conn, "letter"), "Someone Named")


if __name__ == "__main__":
    unittest.main()
