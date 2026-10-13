"""7B run 13 (Qwen2.5 7B on MLE, agent as player): leaving for a named place, finds worked free."""
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-7b-run13-"))
_ENV = isolated_data_env(str(_TMP))
_SAVED_ENV: dict[str, str | None] = {}

T4_LINE = (
    "A hundred and twenty-five. I don't let it show on my face. I leave the docks and walk out onto the flats "
    "toward the drowned lower district while the water's still out."
)
T4_PROSE = (
    "You leave The Docks [[L4]] and step onto the mudflats. The water has just receded, leaving a flat expanse of "
    "wet sand stretching out before you. You walk steadily toward the edge of the mudflats, where the ground starts "
    "to dip into the remnants of the former town."
)
T5_LINE = (
    "I raise a hand to the tide watcher as I pass, then pick the nearest half-buried house and start digging the mud "
    "away from its doorway, looking for anything metal worth hauling back."
)
T5_PROSE = (
    "You raise a hand to the man on the pier as you pass, then kneel by the nearest half-buried house and start "
    "digging the mud away from its doorway. The mud crumbles around your hands, revealing a glint of something shiny. "
    "You tug at a rusted piece of iron, pulling it free. It's not much, but it could be useful."
)


def setUpModule():
    _SAVED_ENV.update({key: os.environ.get(key) for key in _ENV})
    os.environ.update(_ENV)


def tearDownModule():
    for key, value in _SAVED_ENV.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _town_with_docks():
    from app.db import connect, init_db

    init_db()
    with connect() as conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("DELETE FROM npcs")
        conn.execute("DELETE FROM locations")
        conn.execute("INSERT INTO locations (id, code, name, parent_id, kind) VALUES (1, 'L1', 'Saltmarrow', 0, '')")
        conn.execute("INSERT INTO locations (id, code, name, parent_id, kind) VALUES (4, 'L4', 'The Docks', 1, '')")
        if not conn.execute("SELECT 1 FROM player WHERE id = 1").fetchone():
            conn.execute("INSERT INTO player (id, name) VALUES (1, 'Isk')")
        conn.execute("UPDATE player SET current_location_id = 4 WHERE id = 1")


class LeavingForANamedPlace(unittest.TestCase):
    """T4: leaving the docks for the flats stood her in the town square (venue_exit)."""

    def _move(self, line, prose):
        from app import world
        from app.db import connect

        _town_with_docks()
        result = {"narration": prose, "player": {}}
        with connect() as conn:
            intent, _ = world._turn_intent(line)
            report = world.resolve_movement(conn, result, line, intent=intent, narration=prose)
        return report, result["player"].get("move_to_location")

    def test_the_destination_wins(self):
        report, where = self._move(T4_LINE, T4_PROSE)
        self.assertEqual(report.get("rule"), "venue_exit_to", report)
        self.assertEqual(where, "The Flats")

    def test_plain_leaving_still_goes_to_the_town(self):
        report, where = self._move("I leave the docks and walk out.", "You leave the docks behind and walk up into the town.")
        self.assertEqual(report.get("rule"), "venue_exit", report)
        self.assertEqual(where, "Saltmarrow")


class FindWorkedFree(unittest.TestCase):
    """T5: the dig's "rusted piece of iron, pulling it free" granted nothing."""

    def _grant(self, line, prose):
        from app import world
        from app.db import connect, init_db

        init_db()
        with connect() as conn:
            conn.execute("DELETE FROM inventory")
            return world._grant_shown_takes(conn, [], prose, line)

    def test_granted(self):
        added = self._grant(T5_LINE, T5_PROSE)
        self.assertEqual([(a["name"], a["quantity_delta"]) for a in added], [("rusted piece of iron", 1)])

    def test_not_without_a_search(self):
        self.assertEqual(self._grant("I help Abel clear the doorway.", "You tug at a rusted piece of iron, pulling it free."), [])

    def test_not_when_it_goes_back(self):
        added = self._grant(
            T5_LINE,
            "You tug at a rusted piece of iron, pulling it free. It crumbles in your hand, and you toss it aside.",
        )
        self.assertEqual(added, [])


if __name__ == "__main__":
    unittest.main()
