"""m1 (Stell 2026-10-24/25, "go ahead" 2026-10-25): a currency set per world, the purse held as one number.

"i want to add copper, silver and gold as the currency, that way we can translate the currency into 1 form
... $69420 will be translated as 6 gold 94 silver and 20 copper, we should never rely on the llm to work out
the item cost by coin, just a single value". One unit is a copper in the coin set (1 silver = 100, 1 gold =
10,000); credits or bottle caps are their own sets. The purse is player.purse_units (app/purse.py); gold is
its whole-gold mirror. The model writes an amount as $<number> (base units) and the engine shows coins.

Run:  cd tests && ../.venv/bin/python -m unittest test_m1_currency_purse
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
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-m1-currency-"))
_ENV = isolated_data_env(str(_TMP))
_SAVED_ENV: dict[str, str | None] = {}


def setUpModule():
    _SAVED_ENV.update({key: os.environ.get(key) for key in _ENV})
    os.environ.update(_ENV)
    from app.db import init_db

    init_db()


def tearDownModule():
    for key, value in _SAVED_ENV.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _set_world(conn, options: dict | None, currency_set: str | None = None) -> None:
    conn.execute("DELETE FROM settings WHERE key IN ('currency_config', 'playthrough_options')")
    if options is not None:
        conn.execute("INSERT INTO settings (key, value) VALUES ('playthrough_options', ?)", (json.dumps(options),))
    if currency_set:
        from app import currency

        currency.update_currency_config(conn, {"set": currency_set})


class OldSaveMigratesOnce(unittest.TestCase):
    def test_gold_12_becomes_120000_units_once(self):
        from app import db
        from app.db import connect

        with connect().closing() as conn:
            _set_world(conn, {"world_style": "frontier dark fantasy"})
            conn.execute("DELETE FROM settings WHERE key = ?", (db.PURSE_MIGRATED_KEY,))
            conn.execute("UPDATE player SET gold = 12, purse_units = 0 WHERE id = 1")
            conn.commit()
        db.init_db()
        with connect().closing() as conn:
            row = conn.execute("SELECT gold, purse_units FROM player WHERE id = 1").fetchone()
            self.assertEqual((row["gold"], row["purse_units"]), (12, 120000))
            mark = json.loads(conn.execute("SELECT value FROM settings WHERE key = ?", (db.PURSE_MIGRATED_KEY,)).fetchone()[0])
            self.assertEqual(mark, {"set": "coin_medieval", "from_gold": 12, "units": 120000})
            # Spent down to 5 silver: a second start does not migrate again.
            conn.execute("UPDATE player SET gold = 0, purse_units = 500 WHERE id = 1")
            conn.commit()
        db.init_db()
        with connect().closing() as conn:
            row = conn.execute("SELECT gold, purse_units FROM player WHERE id = 1").fetchone()
            self.assertEqual((row["gold"], row["purse_units"]), (0, 500))

    def test_a_legacy_gold_write_is_adopted_in_units(self):
        from app import currency, purse
        from app.db import connect

        cset = currency.theme_set("coin_medieval")
        with connect().closing() as conn:
            conn.execute("UPDATE player SET gold = 12, purse_units = 120500 WHERE id = 1")
            # A tool or an old writer adds 3 gold to the gold column alone.
            conn.execute("UPDATE player SET gold = gold + 3 WHERE id = 1")
            self.assertEqual(purse.purse_units(conn, cset), 150500)
            conn.rollback()


class NewWorldStartsWithItsSet(unittest.TestCase):
    def test_start_purse_per_set(self):
        from app import currency, world
        from app.db import connect

        with connect().closing() as conn:
            currency.update_currency_config(conn, {"set": "scrip"})
            conn.commit()
        for options, set_id, units, gold, shown in (
            ({"world_style": "frontier dark fantasy"}, "coin_medieval", 120000, 12, "12 gold"),
            ({"world_style": "space frontier salvage", "tech_level": "spacefaring salvage"}, "credits", 120, 12,
             "120 credits"),
            ({"world_style": "a fallout rpg in the ruins"}, "caps", 120, 12, "120 caps"),
            ({"world_style": "frontier dark fantasy", "currency_set": "credits"}, "credits", 120, 12, "120 credits"),
        ):
            with self.subTest(set=set_id, options=options):
                # The last world's set (scrip, then each one before) is not this world's.
                world.start_playthrough({"player_name": "Wren", "start_location": "Low Gate", **options})
                with connect().closing() as conn:
                    row = conn.execute("SELECT gold, purse_units FROM player WHERE id = 1").fetchone()
                    self.assertEqual((row["purse_units"], row["gold"]), (units, gold))
                    self.assertEqual(currency.get_currency_config(conn)["set"], set_id)
                state = world.get_state()
                self.assertEqual(state["purse"]["units"], units)
                self.assertEqual(state["purse"]["set"], set_id)
                self.assertEqual(state["purse"]["long"], shown)
                self.assertEqual(state["player"]["gold"], gold)


if __name__ == "__main__":
    unittest.main()
