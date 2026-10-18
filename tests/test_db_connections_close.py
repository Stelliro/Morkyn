"""A ``with connect() as conn:`` block closes its connection (8B run 150: ~70 handles leaked a turn).

Run:  .venv\\Scripts\\python -m unittest tests.test_db_connections_close
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-dbclose-"))
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


class TheBlockClosesItsConnection(unittest.TestCase):
    def test_closed_after_the_block(self):
        from app.db import connect, init_db

        init_db()
        with connect().closing() as conn:
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('probe', '1')")
        with self.assertRaises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")
        with connect().closing() as again:
            row = again.execute("SELECT value FROM settings WHERE key = 'probe'").fetchone()
        self.assertEqual(row[0], "1")  # the write was committed before the close

    def test_a_held_connection_survives_its_commit_block(self):
        from app.db import connect, init_db

        init_db()
        held = connect()
        try:
            with held:
                held.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('probe2', '2')")
            self.assertEqual(held.execute("SELECT value FROM settings WHERE key = 'probe2'").fetchone()[0], "2")
        finally:
            held.close()

    def test_the_engine_uses_closing_blocks(self):
        import re

        bare = []
        for path in (ROOT / "app").glob("*.py"):
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if re.search(r"\bwith (?:connect|_db_connect)\(\) as ", line):
                    bare.append(f"{path.name}:{n}")
        self.assertEqual(bare, [], "with connect() as ... never closes; use connect().closing()")

    def test_init_db_runs_twice(self):
        from app.db import init_db

        init_db()
        init_db()


if __name__ == "__main__":
    unittest.main()
