"""8B run 151: faults fixed by class.

T6: "He slides a small bundle across the table, damp cloth wrapped around a
rusted key" refused GRANT "rusty key" as never arriving.
Run 150 T84 (fixed here): a natural 1 on a plain question wrote "A brutal
miss: something breaks, bleeds, or betrays you".

Run:  .venv\\Scripts\\python -m unittest tests.test_8b_run151
"""
from __future__ import annotations

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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-run151-"))
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
        for i, (name, qty) in enumerate(names):
            conn.execute("INSERT INTO inventory (code, name, quantity) VALUES (?, ?, ?)", (f"I{i + 1}", name, qty))


def _filter(changes, narration, line):
    from app import world
    from app.db import connect

    rejected: list = []
    with connect() as conn:
        kept = world._filter_inventory_changes(conn, changes, narration=narration, player_input=line, rejected=rejected)
    return kept, rejected


class AThingHandedInAWrapping(unittest.TestCase):
    LINE = "\"Then put me on the books. What's the first job, and what does it pay?\" I hold out my hand to be given the work."
    PROSE = ("Wymarc Fletcher's fingers tap a ledger, then snap shut. “That's why I've got a job for you.” He slides a "
             "small bundle across the table—damp cloth wrapped around a rusted key. “This opens the lock on the old "
             "warehouse by the docks.”")

    def test_the_key_in_the_bundle_arrives(self):
        _pack()
        kept, rejected = _filter([{"name": "rusty key", "quantity_delta": 1}], self.PROSE, self.LINE)
        self.assertEqual([c["name"] for c in kept], ["rusty key"], rejected)


class FixingANameInMemoryIsNoWork(unittest.TestCase):
    """T13: "read the name aloud to fix it in my memory" rolled a craft check and cost energy."""

    def test_no_act(self):
        from app.prose_state import act_rules

        self.assertIsNone(act_rules("I pocket the coin and read the name in the last entry aloud to fix it in my memory."))
        self.assertIsNotNone(act_rules("I fix the broken latch on the chest."))


class _One(random.Random):
    def randint(self, a, b):  # noqa: D401 - a die that always shows 1
        return a


class RoutineTalkFailsAtWorst(unittest.TestCase):
    OPPOSITION = {"name": "Mabel", "attribute": "charisma", "stat_score": 10, "power_total": 8}

    def test_a_natural_one_on_a_plain_question_is_no_brutal_miss(self):
        from app.skill_checks import resolve_check

        result = resolve_check(skill_code="persuasion", player_stats={"charisma": 10}, player_skills=[],
                               opposition=self.OPPOSITION, rng=_One(), routine=True)
        self.assertEqual(result.get("outcome"), "failure", result)
        self.assertFalse(result.get("mishap"), result)

    def test_a_natural_one_on_a_real_push_still_fumbles(self):
        from app.skill_checks import resolve_check

        result = resolve_check(skill_code="persuasion", player_stats={"charisma": 10}, player_skills=[],
                               opposition=self.OPPOSITION, rng=_One(), routine=False)
        self.assertEqual(result.get("outcome"), "critical_failure", result)


if __name__ == "__main__":
    unittest.main()
