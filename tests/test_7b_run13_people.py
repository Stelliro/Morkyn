"""7B run 13 (Qwen2.5 7B on MLE, agent as player): a job is not a name, and its one holder keeps theirs."""
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-7b-run13-people-"))
_ENV = isolated_data_env(str(_TMP))
_SAVED_ENV: dict[str, str | None] = {}

PEOPLE = [
    ("A", "Percival Oakes", "miller"),
    ("B", "Gunilda Fowler", "woodseller"),
    ("E", "Rosamund Colley", "harbour reeve"),
]


def setUpModule():
    _SAVED_ENV.update({key: os.environ.get(key) for key in _ENV})
    os.environ.update(_ENV)


def tearDownModule():
    for key, value in _SAVED_ENV.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _town():
    """Saltmarrow with the docks inside it, the player on the docks, and the run-13 people in town."""
    from app.db import connect, init_db

    init_db()
    with connect() as conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        for table in ("npcs", "locations"):
            conn.execute(f"DELETE FROM {table}")
        conn.execute("INSERT INTO locations (id, code, name, parent_id) VALUES (1, 'L1', 'Saltmarrow', 0)")
        conn.execute("INSERT INTO locations (id, code, name, parent_id) VALUES (4, 'L4', 'The Docks', 1)")
        if not conn.execute("SELECT 1 FROM player WHERE id = 1").fetchone():
            conn.execute("INSERT INTO player (id, name) VALUES (1, 'Isk')")
        conn.execute("UPDATE player SET current_location_id = 4 WHERE id = 1")
        for code, name, role in PEOPLE:
            conn.execute(
                "INSERT INTO npcs (code, location_id, name, role) VALUES (?, 1, ?, ?)", (code, name, role)
            )


class ARoleIsNotAName(unittest.TestCase):
    """T5: NPC_NEW "E" "Harbour reeve" minted a person called 'Harbour reeve'."""

    def setUp(self):
        _town()

    def test_role_phrase(self):
        from app.world import _role_phrase

        self.assertEqual(_role_phrase("Harbour reeve"), "harbour reeve")
        self.assertEqual(_role_phrase("the miller"), "miller")
        self.assertEqual(_role_phrase("Rosamund Colley"), "")
        self.assertEqual(_role_phrase("Isk"), "")

    def test_resolves_to_the_holder(self):
        from app import world
        from app.db import connect

        with connect() as conn:
            npc = {"code": "E", "name": "Harbour reeve", "role": "REEVE Saltmarrow observant"}
            npc_id = world._upsert_npc(conn, npc)
            row = conn.execute("SELECT name FROM npcs WHERE id = ?", (npc_id,)).fetchone()
            count = conn.execute("SELECT COUNT(*) FROM npcs").fetchone()[0]
        self.assertEqual(row["name"], "Rosamund Colley")
        self.assertEqual(count, len(PEOPLE))

    def test_resolves_without_the_code(self):
        from app import world
        from app.db import connect

        with connect() as conn:
            npc_id = world._upsert_npc(conn, {"name": "the harbour reeve", "role": ""})
            row = conn.execute("SELECT name FROM npcs WHERE id = ?", (npc_id,)).fetchone()
        self.assertEqual(row["name"], "Rosamund Colley")

    def test_nobody_holds_it_draws_a_name(self):
        from app import world
        from app.db import connect

        with connect() as conn:
            npc_id = world._upsert_npc(conn, {"name": "Tide watcher", "role": ""})
            row = conn.execute("SELECT name, role FROM npcs WHERE id = ?", (npc_id,)).fetchone()
        self.assertNotEqual(row["name"].lower(), "tide watcher")
        self.assertEqual(row["role"], "tide watcher")


class RoleNameDrift(unittest.TestCase):
    def setUp(self):
        _town()

    def test_unknown_name_for_the_holder(self):
        """T2: 'the Reeve, Gwenllian Tolley' for Rosamund Colley."""
        from app import world
        from app.db import connect

        text = ("You stand at the edge of the lower district, your eyes fixed on the Reeve, Gwenllian Tolley, who "
                "stands a few steps away. Tolley's expression remains neutral.")
        with connect() as conn:
            fixed, changes = world._repair_role_name_drift(conn, text)
        self.assertIn("the Reeve, Rosamund Colley,", fixed)
        self.assertIn("Colley's expression", fixed)
        self.assertNotIn("Tolley", fixed)
        self.assertEqual(changes[0]["why"], "role_name_drift")

    def test_title_on_the_wrong_person_goes(self):
        """T3: 'Reeve Percival Oakes' / 'Reeve Oakes' for the miller."""
        from app import world
        from app.db import connect

        text = "You step closer to Reeve Percival Oakes, who stands by the cookshop. Reeve Oakes shifts his weight."
        with connect() as conn:
            fixed, changes = world._repair_role_name_drift(conn, text)
        self.assertEqual(fixed, "You step closer to Percival Oakes, who stands by the cookshop. Oakes shifts his weight.")
        self.assertEqual([c["why"] for c in changes], ["wrong_title", "wrong_title"])

    def test_right_title_and_known_names_stay(self):
        from app import world
        from app.db import connect

        text = "Reeve Rosamund Colley nods to Gunilda Fowler, the woodseller, and the miller, Percival Oakes."
        with connect() as conn:
            fixed, changes = world._repair_role_name_drift(conn, text)
        self.assertEqual((fixed, changes), (text, []))


class IntroducedBesideAHint(unittest.TestCase):
    """T4: 'a figure catches your eye. Stephen Lambard, a tide watcher, is standing ...' stored nobody."""

    def setUp(self):
        _town()

    def test_the_introduced_person_is_stored(self):
        from app import world
        from app.db import connect

        text = ("The ruins loom ahead. As you approach, a figure catches your eye. Stephen Lambard, a tide watcher, "
                "is standing on a slight rise, his hands folded behind his back.")
        with connect() as conn:
            created = world._ensure_npcs_from_narration(conn, {}, text, 4)
            names = [r["name"] for r in conn.execute("SELECT name, role FROM npcs")]
        self.assertEqual([c["name"] for c in created], ["Stephen Lambard"])
        self.assertIn("Stephen Lambard", names)


if __name__ == "__main__":
    unittest.main()
