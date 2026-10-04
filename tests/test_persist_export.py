"""Reload keeps player relationships and quests.

Those tables were left out of the world export, so a save/load dropped them
while people, items, and the map came back. Run:

    python -m unittest tests.test_persist_export
"""

from __future__ import annotations

import gc
import json
import os
import tempfile
import unittest
import warnings
from pathlib import Path

from app.db import connect, db_path, init_db
from app.quests import create_quest
from app.relationships import update_relationship
from app.world import export_world, import_world, start_playthrough

_ENV = (
    "AI_RPG_DB",
    "AI_RPG_CAMPAIGN_SLOTS",
    "AI_RPG_MODEL_TRACE_DIR",
    "AI_RPG_HISTORY_SUMMARY",
    "AI_RPG_SOURCE_INDEX",
    "AI_RPG_CONSOLIDATED_FACTS",
    "AI_RPG_SETTING_TEMPLATES",
)
_LIVE_DB = Path(__file__).resolve().parent.parent / "data" / "world.db"


class PersistExportTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="morkyn-persist-export-")
        root = Path(self._tmp.name)
        self._saved = {key: os.environ.get(key) for key in _ENV}
        os.environ["AI_RPG_DB"] = str(root / "world.db")
        os.environ["AI_RPG_CAMPAIGN_SLOTS"] = str(root / "slots")
        os.environ["AI_RPG_MODEL_TRACE_DIR"] = str(root / "traces")
        os.environ["AI_RPG_HISTORY_SUMMARY"] = str(root / "history.jsonl")
        os.environ["AI_RPG_SOURCE_INDEX"] = str(root / "source")
        os.environ["AI_RPG_CONSOLIDATED_FACTS"] = str(root / "facts.jsonl")
        os.environ["AI_RPG_SETTING_TEMPLATES"] = "0"
        self.assertNotEqual(Path(db_path()).resolve(), _LIVE_DB.resolve())
        self.assertTrue(str(db_path()).startswith(str(root)))

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)
            gc.collect()
        self._tmp.cleanup()

    def _seed(self) -> None:
        init_db()
        conn = connect()
        try:
            loc = conn.execute("SELECT id FROM locations LIMIT 1").fetchone()
            conn.execute(
                "INSERT INTO npcs (code, name, location_id) VALUES ('A', 'Mara Quill', ?)",
                (int(loc["id"]),),
            )
            npc_id = int(conn.execute("SELECT id FROM npcs WHERE code = 'A'").fetchone()["id"])
            update_relationship(
                conn,
                npc_id,
                affinity_delta=40,
                fear_delta=5,
                respect_delta=12,
                reason="helped",
            )
            create_quest(
                conn,
                title="Carry the sealed letter",
                description="Take it to the gate.",
                giver_npc_id=npc_id,
                steps=[
                    {
                        "title": "Leave the inn",
                        "description": "Walk out.",
                        "location_name": "Gate",
                    }
                ],
            )
            conn.execute(
                "INSERT INTO world_maps (id, player_x, player_y) VALUES ('m1', 12959, 13397)"
            )
            conn.commit()
        finally:
            conn.close()

    def test_reload_restores_relationships_and_quests(self):
        self._seed()
        payload = json.loads(json.dumps(export_world()))
        tables = payload["tables"]
        self.assertEqual(len(tables["quests"]), 1)
        self.assertEqual(len(tables["quest_steps"]), 1)
        self.assertEqual(len(tables["npc_player_relationships"]), 1)
        self.assertEqual(tables["npc_player_relationships"][0]["affinity"], 40)
        self.assertEqual(tables["world_maps"][0]["player_x"], 12959)

        import_world(payload)
        conn = connect()
        try:
            rel = conn.execute(
                "SELECT affinity, fear, respect, last_interaction FROM npc_player_relationships"
            ).fetchone()
            self.assertEqual(int(rel["affinity"]), 40)
            self.assertEqual(int(rel["fear"]), 5)
            self.assertEqual(int(rel["respect"]), 12)
            self.assertEqual(rel["last_interaction"], "helped")
            quest = conn.execute("SELECT id, title, giver_npc_id FROM quests").fetchone()
            step = conn.execute("SELECT title, quest_id FROM quest_steps").fetchone()
            npc = conn.execute("SELECT id FROM npcs WHERE code = 'A'").fetchone()
            self.assertEqual(quest["title"], "Carry the sealed letter")
            self.assertEqual(step["title"], "Leave the inn")
            self.assertEqual(int(step["quest_id"]), int(quest["id"]))
            self.assertEqual(int(quest["giver_npc_id"]), int(npc["id"]))
            spot = conn.execute("SELECT player_x, player_y FROM world_maps").fetchone()
            self.assertEqual(int(spot["player_x"]), 12959)
            self.assertEqual(int(spot["player_y"]), 13397)
        finally:
            conn.close()

    def test_old_slot_without_the_keys_does_not_wipe_them(self):
        self._seed()
        payload = json.loads(json.dumps(export_world()))
        for key in ("quests", "quest_steps", "npc_player_relationships", "world_maps"):
            payload["tables"].pop(key)
        conn = connect()
        try:
            conn.execute("UPDATE npc_player_relationships SET affinity = 7")
            conn.execute("UPDATE world_maps SET player_x = 8")
            conn.commit()
        finally:
            conn.close()

        import_world(payload)
        conn = connect()
        try:
            rel = conn.execute("SELECT affinity FROM npc_player_relationships").fetchone()
            quests = conn.execute("SELECT COUNT(*) AS c FROM quests").fetchone()["c"]
            steps = conn.execute("SELECT COUNT(*) AS c FROM quest_steps").fetchone()["c"]
            spot = conn.execute("SELECT player_x FROM world_maps").fetchone()
            self.assertEqual(int(rel["affinity"]), 7)
            self.assertEqual(int(quests), 1)
            self.assertEqual(int(steps), 1)
            self.assertEqual(int(spot["player_x"]), 8)
        finally:
            conn.close()

    def test_empty_lists_clear_and_a_new_playthrough_starts_clean(self):
        self._seed()
        payload = json.loads(json.dumps(export_world()))
        for key in ("quests", "quest_steps", "npc_player_relationships"):
            payload["tables"][key] = []
        import_world(payload)
        conn = connect()
        try:
            quests = conn.execute("SELECT COUNT(*) AS c FROM quests").fetchone()["c"]
            steps = conn.execute("SELECT COUNT(*) AS c FROM quest_steps").fetchone()["c"]
            rels = conn.execute(
                "SELECT COUNT(*) AS c FROM npc_player_relationships"
            ).fetchone()["c"]
            self.assertEqual(int(quests), 0)
            self.assertEqual(int(steps), 0)
            self.assertEqual(int(rels), 0)
            npc_id = int(conn.execute("SELECT id FROM npcs WHERE code = 'A'").fetchone()["id"])
            update_relationship(conn, npc_id, affinity_delta=3, reason="again")
            create_quest(
                conn,
                title="Again",
                steps=[{"title": "Step", "description": "Go."}],
            )
            conn.commit()
        finally:
            conn.close()

        start_playthrough({"player_name": "Mara Vale", "special_ability_origin": "none"})
        conn = connect()
        try:
            quests = conn.execute("SELECT COUNT(*) AS c FROM quests").fetchone()["c"]
            steps = conn.execute("SELECT COUNT(*) AS c FROM quest_steps").fetchone()["c"]
            rels = conn.execute(
                "SELECT COUNT(*) AS c FROM npc_player_relationships"
            ).fetchone()["c"]
            self.assertEqual(int(quests), 0)
            self.assertEqual(int(steps), 0)
            self.assertEqual(int(rels), 0)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
