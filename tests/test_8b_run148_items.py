"""8B run 148, T39: a thing granted under an article is the thing already carried.

GRANT "a rusted iron key" went into the pack beside the "rusted iron key" the
player already held, because the inventory write matched the stored name
exactly. The pack holds things, not phrases: a leading article is no part of a
name, and a grant under another article or case lands on the row it names.

Run:  .venv\\Scripts\\python -m unittest tests.test_8b_run148_items
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-run148-items-"))
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


def _pack(*names):
    from app.db import connect, init_db

    init_db()
    with connect() as conn:
        conn.execute("DELETE FROM inventory")
        for name, qty in names:
            conn.execute("INSERT INTO inventory (name, quantity) VALUES (?, ?)", (name, qty))


def _rows():
    from app.db import connect

    with connect() as conn:
        return {str(r["name"]): int(r["quantity"]) for r in conn.execute("SELECT name, quantity FROM inventory WHERE quantity > 0")}


class AGrantUnderAnArticle(unittest.TestCase):
    def test_a_rusted_iron_key_is_the_rusted_iron_key_carried(self):
        from app import world
        from app.db import connect

        _pack(("rusted iron key", 1))
        with connect() as conn:
            world._apply_inventory(conn, [{"name": "a rusted iron key", "quantity_delta": 1}])
        self.assertEqual(_rows(), {"rusted iron key": 2})

    def test_the_stored_article_matches_too(self):
        from app import world
        from app.db import connect

        _pack(("a broken compass", 1))
        with connect() as conn:
            world._apply_inventory(conn, [{"name": "Broken Compass", "quantity_delta": 1}])
        self.assertEqual(_rows(), {"a broken compass": 2})

    def test_a_new_thing_is_stored_without_its_article(self):
        from app import world
        from app.db import connect

        _pack()
        with connect() as conn:
            world._apply_inventory(conn, [{"name": "an oilskin pouch", "quantity_delta": 1}])
        self.assertEqual(_rows(), {"oilskin pouch": 1})

    def test_a_loss_under_an_article_leaves_the_pack_right(self):
        from app import world
        from app.db import connect

        _pack(("cod fillets", 2))
        with connect() as conn:
            world._apply_inventory(conn, [{"name": "the cod fillets", "quantity_delta": -1}])
        self.assertEqual(_rows(), {"cod fillets": 1})

    def test_another_thing_is_not_matched(self):
        from app import world
        from app.db import connect

        _pack(("iron key", 1))
        with connect() as conn:
            world._apply_inventory(conn, [{"name": "a brass key", "quantity_delta": 1}])
        self.assertEqual(_rows(), {"iron key": 1, "brass key": 1})


if __name__ == "__main__":
    unittest.main()
