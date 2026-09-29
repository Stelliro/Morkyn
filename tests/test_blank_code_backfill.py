"""Blank entity codes must not be refilled with an id that is already taken.

init_db used to set a blank NPC at id 2 to B, and a blank place at id 2 to L2.
If B or L2 already belonged to another row, the UNIQUE index aborted startup.

Run: python -m unittest tests.test_blank_code_backfill
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-blank-code-"))
os.environ.update(
    {
        "AI_RPG_DB": str(_TMP / "world.db"),
        "AI_RPG_PACK_DIR": str(_TMP / "packs"),
        "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
        "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
        "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
        "AI_RPG_CAMPAIGN_SLOTS": str(_TMP / "slots"),
    }
)

from app.db import connect, init_db  # noqa: E402

init_db()


class BlankCodeBackfillTests(unittest.TestCase):
    def test_second_init_does_not_collide_with_a_taken_code(self):
        with connect() as conn:
            conn.execute("INSERT INTO locations (code, name, summary) VALUES ('L2', 'Taken Gate', '')")
            loc_id = conn.execute("SELECT id FROM locations WHERE code = 'L2'").fetchone()["id"]
            conn.execute("INSERT INTO locations (code, name, summary) VALUES ('', 'Blank Place', '')")
            conn.execute(
                "INSERT INTO npcs (code, location_id, name) VALUES ('B', ?, 'Taken')",
                (loc_id,),
            )
            conn.execute(
                "INSERT INTO npcs (code, location_id, name) VALUES ('', ?, 'Blank')",
                (loc_id,),
            )

        init_db()

        with connect() as conn:
            npcs = {
                row["name"]: row["code"]
                for row in conn.execute("SELECT name, code FROM npcs")
            }
            places = {
                row["name"]: row["code"]
                for row in conn.execute("SELECT name, code FROM locations")
            }
        self.assertEqual(npcs["Taken"], "B")
        self.assertTrue(npcs["Blank"])
        self.assertNotEqual(npcs["Blank"], "B")
        self.assertEqual(len(set(npcs.values())), len(npcs))
        self.assertEqual(places["Taken Gate"], "L2")
        self.assertTrue(places["Blank Place"])
        self.assertNotEqual(places["Blank Place"], "L2")
        self.assertEqual(len(set(places.values())), len(places))


if __name__ == "__main__":
    unittest.main()
