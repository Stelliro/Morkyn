"""Fixes from the fourth Saltmarrow run on Qwen2.5 7B (MLE), the player played by an agent."""
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-7b-run4-"))
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


class JobWordIsNotAName(unittest.TestCase):
    """T1: NPC_NEW A "tinker" "Helewise Eastlake" "off" made a person called 'tinker'."""

    def test_name_and_job_swap_back(self):
        from app.turn_dsl import _classify_npc_args

        out = _classify_npc_args(["A", "tinker", "Helewise Eastlake", "off"])
        self.assertEqual(out["name"], "Helewise Eastlake")
        self.assertEqual(out["role"], "tinker")

    def test_ordinary_orders_unchanged(self):
        from app.turn_dsl import _classify_npc_args

        out = _classify_npc_args(["Helewise Eastlake", "tinker", "L1"])
        self.assertEqual((out["name"], out["role"], out["location"]), ("Helewise Eastlake", "tinker", "L1"))
        out = _classify_npc_args(["Umar", "Mendes", "carter"])
        self.assertEqual((out["name"], out["role"]), ("Umar Mendes", "carter"))


class AnAsideIsNotATake(unittest.TestCase):
    """T1: 'You take the pocket watch, the weight of the coins in your hand ...' granted 'weight'."""

    def _run(self, line, prose, changes=()):
        from app import world
        from app.db import connect, init_db

        init_db()
        with connect() as conn:
            conn.execute("DELETE FROM inventory")
            return world._grant_shown_takes(conn, list(changes), prose, line)

    def test_weight_of_the_coins_is_not_granted(self):
        prose = (
            "You take the pocket watch, the weight of the coins in your hand a reminder of the trade you've made."
        )
        line = "Morning, Helewise. Anything on there that'll keep the time better than this?"
        added = self._run(line, prose, [{"name": "small pocket watch", "quantity_delta": 1}])
        self.assertEqual([c["name"] for c in added], ["small pocket watch"])

    def test_a_real_list_still_counts(self):
        added = self._run(
            "I take the rusty key, the faded map and the candle.",
            "You take the rusty key, the faded map and the candle from the drawer.",
        )
        self.assertEqual(sorted(c["name"] for c in added), ["candle", "faded map", "rusty key"])

    def test_take_whatever_still_counts(self):
        added = self._run(
            "I pocket whatever is under it.",
            "Beneath it lies a silver coin, dull with age. You pocket it.",
        )
        self.assertEqual([c["name"] for c in added], ["silver coin"])


if __name__ == "__main__":
    unittest.main()
