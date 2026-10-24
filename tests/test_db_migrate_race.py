"""Two connections migrating one save at once: the second's "duplicate column" is a re-read, not an error.

The game and its read-only viewer thread (tools/api_bridge_playtest.py --viewer-port) both
ran init_db at start; the viewer died with ``sqlite3.OperationalError: duplicate column name:
body`` (sonnet100 launch 1, 2026-10-25). The column existing is what the migration wanted.

Run:  .venv/bin/python -m unittest tests.test_db_migrate_race
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-dbrace-"))
_ENV = isolated_data_env(str(_TMP))
_SAVED_ENV: dict[str, str | None] = {}


def setUpModule():
    _SAVED_ENV.update({key: os.environ.get(key) for key in _ENV})
    os.environ.update(_ENV)


def tearDownModule():
    for key, value in _SAVED_ENV.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


class DuplicateColumnIsARead(unittest.TestCase):
    def test_a_column_another_connection_added_first_is_skipped(self):
        from app import db

        db.init_db()
        real = db._migrate_columns
        calls: list[int] = []

        def racing(conn):
            calls.append(1)
            if len(calls) == 1:
                # The other connection's ALTER landed between our read and ours.
                raise sqlite3.OperationalError("duplicate column name: body")
            return real(conn)

        with mock.patch.object(db, "_migrate_columns", racing):
            db.init_db()
        self.assertEqual(len(calls), 2)
        with db.connect().closing() as conn:
            names = {row[1] for row in conn.execute("PRAGMA table_info(npcs)")}
        self.assertIn("body", names)

    def test_any_other_error_still_raises(self):
        from app import db

        db.init_db()
        with mock.patch.object(db, "_migrate_columns", side_effect=sqlite3.OperationalError("database is locked")):
            with self.assertRaises(sqlite3.OperationalError):
                db.init_db()


if __name__ == "__main__":
    unittest.main()
