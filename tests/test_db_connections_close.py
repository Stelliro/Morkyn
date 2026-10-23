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


def _bare_connect_blocks(source: str, label: str) -> list[str]:
    """`with X() as` blocks whose X is app.db.connect under any name, or sqlite3.connect.

    The names come from the file's own imports (``from app.db import connect as
    _connect``, ``from app import db as _db``), so a new alias is caught without
    a new pattern. ``X().closing()`` is the closing form and is not listed.
    """
    import ast

    tree = ast.parse(source)
    funcs = {"connect", "_db_connect"}  # bare names bound to app.db.connect
    modules = {"db", "sqlite3"}  # module names whose .connect() opens a connection
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in {"app.db", "db"}:
            for alias in node.names:
                if alias.name == "connect":
                    funcs.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module == "app":
            for alias in node.names:
                if alias.name == "db":
                    modules.add(alias.asname or "db")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in {"app.db", "sqlite3"} and alias.asname:
                    modules.add(alias.asname)
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.With, ast.AsyncWith)):
            continue
        for item in node.items:
            call = item.context_expr
            if not isinstance(call, ast.Call):
                continue
            target = call.func
            if isinstance(target, ast.Name) and target.id in funcs:
                found.append(f"{label}:{node.lineno}")
            elif (
                isinstance(target, ast.Attribute)
                and target.attr == "connect"
                and isinstance(target.value, ast.Name)
                and target.value.id in modules
            ):
                found.append(f"{label}:{node.lineno}")
    return found


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
        bare = []
        for path in sorted((ROOT / "app").rglob("*.py")):
            bare.extend(_bare_connect_blocks(path.read_text(encoding="utf-8"), path.name))
        self.assertEqual(bare, [], "with connect() as ... never closes; use connect().closing()")

    def test_the_scan_catches_every_alias(self):
        # Playtest #162: main.py's `from app.db import connect as _connect` then
        # `with _connect() as conn:` passed the old pattern, which knew only
        # connect() and _db_connect().
        source = (
            "from app.db import connect as _connect\n"
            "from app import db as _db\n"
            "import sqlite3\n"
            "def f():\n"
            "    from app.db import connect as _c\n"
            "    with _connect() as conn:\n"
            "        pass\n"
            "    with _c() as c2:\n"
            "        pass\n"
            "    with _db.connect() as c3:\n"
            "        pass\n"
            "    with sqlite3.connect('x.db') as c4:\n"
            "        pass\n"
            "    with _connect().closing() as ok:\n"
            "        pass\n"
            "    with open('x') as fine:\n"
            "        pass\n"
        )
        self.assertEqual(_bare_connect_blocks(source, "probe.py"), ["probe.py:6", "probe.py:8", "probe.py:10", "probe.py:12"])

    def test_init_db_runs_twice(self):
        from app.db import init_db

        init_db()
        init_db()


if __name__ == "__main__":
    unittest.main()
