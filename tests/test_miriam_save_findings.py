"""
Regressions from the "Miriam Shaw" save (campaign fdf588b2, turns 1-3).

* `NPC_NEW Dockwick "Dockwick" carter L1 friendly` put the carter in a new
  location called "Dockwick".
* Replacement names Ivycoil / Ivywick / Ivyfield, and an NPC sharing a place's name.
* Two of three history summaries read "response: scene advanced with DSL ops."
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_TMP = Path(tempfile.mkdtemp(prefix="morkyn-miriam-"))
os.environ.update(
    {
        "AI_RPG_DB": str(_TMP / "world.db"),
        "AI_RPG_PACK_DIR": str(_TMP / "packs"),
        "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
        "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
        "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
    }
)

from app import db, turn_dsl, world  # noqa: E402
from app.db import connect  # noqa: E402


class TestNpcNewArguments(unittest.TestCase):
    def test_a_bare_name_is_never_a_location(self):
        out = turn_dsl._classify_npc_args(["Dockwick", "Dockwick", "carter", "L1", "friendly"])
        self.assertEqual(out, {"name": "Dockwick", "location": "L1", "role": "carter", "attitude": "friendly"})

    def test_a_leading_code_is_skipped(self):
        out = turn_dsl._classify_npc_args(["A1", "Mara Venn", "baker"])
        self.assertEqual((out["name"], out["role"], out["location"]), ("Mara Venn", "baker", ""))


class TestReplacementNames(unittest.TestCase):
    def test_names_avoid_places_and_shared_first_parts(self):
        db.init_db()
        world.start_playthrough({"player_name": "T", "start_location": "Dockwick", "special_ability_origin": "none"})
        with connect() as conn:
            names = []
            for i in range(8):
                name = world.unique_person_name(conn, seed=1234 + i)
                conn.execute("INSERT INTO npcs (code, name, location_id) VALUES (?, ?, 1)", (f"Z{i}", name))
                names.append(name)
        self.assertNotIn("Dockwick", names)
        firsts = [next((p for p in world._SHELL_NAME_PARTS_A if n.startswith(p)), n) for n in names]
        self.assertEqual(len(firsts), len(set(firsts)), names)


class TestSummariesSayWhatHappened(unittest.TestCase):
    def test_the_fallback_summary_quotes_the_scene(self):
        turn = turn_dsl.ops_to_turn("You step closer to the lantern [[I2]]. Dockwick warns you off.", [], "investigate glowing lantern")
        self.assertNotIn("DSL ops", turn["turn_summary"])
        self.assertIn("Dockwick warns you off", turn["turn_summary"])

    def test_the_opening_does_not_repeat_the_internal_request(self):
        turn = turn_dsl.ops_to_turn("You stand at the caravanserai.", [], "__opening_scene_request__: Begin the playthrough")
        self.assertTrue(turn["turn_summary"].startswith("opening: You stand"))



class TestStaleServerNotice(unittest.TestCase):
    """The save was set up by a new page against an old server process."""

    def test_changed_python_after_start_raises_the_notice(self):
        from app import main

        saved = dict(main._STARTUP_PYTHON_STAMP)
        try:
            self.assertIsNone(main._stale_server_notice())
            main._STARTUP_PYTHON_STAMP["world.py"] = saved.get("world.py", 0.0) - 60.0
            notice = main._stale_server_notice()
            self.assertEqual(notice["code"], "stale_server")
            self.assertIn("world.py", notice["detail"])
            self.assertEqual(main._context_notice_safely()["code"], "stale_server")
        finally:
            main._STARTUP_PYTHON_STAMP.clear()
            main._STARTUP_PYTHON_STAMP.update(saved)


class TestTurnHistoryRoute(unittest.TestCase):
    """The scene history's "View more" pages back past the page's journal window."""

    def test_older_turns_come_newest_first_with_a_more_flag(self):
        from app import main

        db.init_db()
        world.start_playthrough({"player_name": "T", "start_location": "Low Gate", "special_ability_origin": "none"})
        with connect() as conn:
            for t in range(1, 26):
                conn.execute("INSERT INTO journal (turn, kind, content) VALUES (?, 'player', ?)", (t, f"act {t}"))
                conn.execute("INSERT INTO journal (turn, kind, content) VALUES (?, 'narration', ?)", (t, f"scene {t}"))
            conn.commit()
        page = main.api_turn_history(before=20, limit=10)
        self.assertEqual([t["turn"] for t in page["turns"]], list(range(19, 9, -1)))
        self.assertTrue(page["has_more"])
        self.assertEqual({e["kind"] for e in page["turns"][0]["entries"]} >= {"player", "narration"}, True)
        last = main.api_turn_history(before=4, limit=10)
        self.assertEqual([t["turn"] for t in last["turns"]], [3, 2, 1])
        self.assertFalse(last["has_more"])
        self.assertEqual(main.api_turn_history(before=1)["turns"], [])

if __name__ == "__main__":
    unittest.main()
