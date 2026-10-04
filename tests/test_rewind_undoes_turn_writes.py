"""Rewind and Regenerate undo everything the turn wrote.

Two gaps in the `ai-rpg-delta-v1` record:

* Quest tables were outside it while `tick_quest_timers` ran on every
  `apply_turn`, so a regenerated turn ticked a timed quest twice and could
  fail it a turn early; offers posted inside the turn stayed.
* `play_turn` committed the social check's `npcs.attitude`/`trust`, the
  `last_social` setting and the write-once pronoun pin before `apply_turn`
  took the snapshot, and settings were never snapshotted, so a rewind kept
  them and a regenerated turn stacked trust a second time.

Run:  python -m unittest tests.test_rewind_undoes_turn_writes
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-rewind-test-"))
_ENV = {
    "AI_RPG_DB": str(_TMP / "world.db"),
    "AI_RPG_PACK_DIR": str(_TMP / "packs"),
    "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
    "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
    "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
    "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
    "AI_RPG_CAMPAIGN_SLOTS": str(_TMP / "slots"),
}
os.environ.update(_ENV)

from app import db, local_intel, quests, world  # noqa: E402


def setUpModule():
    os.environ.update(_ENV)
    assert str(db.db_path()).startswith(str(_TMP)), db.db_path()
    db.init_db()


def _fresh_world():
    db.init_db()
    world.start_playthrough({"player_name": "Ash", "start_location": "Low Gate", "special_ability_origin": "none"})


def _turn(narration: str) -> dict:
    return {
        "scene_plan": {"goal": "look", "focus_points": []},
        "narration_segments": [{"label": "scene", "text": narration}],
        "narration": narration,
        "player": {},
        "self_check": {"passed": True, "issues_found": [], "corrections_made": []},
        "turn_summary": "a beat",
        "scene_focus": "action",
    }


def _play(narration: str, player_input: str = "I look around") -> dict:
    with mock.patch.object(world, "generate_turn", return_value=_turn(narration)):
        return world.play_turn(player_input)


def _regenerate(narration: str) -> dict:
    with mock.patch.object(world, "generate_turn", return_value=_turn(narration)):
        return world.regenerate_last_turn()


def _timed_quest(turns: int) -> int:
    with db.connect() as conn:
        return quests.create_quest(
            conn,
            title="Before the Gate Closes",
            steps=[{"title": "Reach the gate", "description": "Get there."}],
            timer_turns=turns,
        )


def _remaining(quest_id: int):
    with db.connect() as conn:
        row = conn.execute("SELECT turns_remaining, status FROM quests WHERE id = ?", (quest_id,)).fetchone()
    return (int(row["turns_remaining"]), str(row["status"])) if row else None


def _add_npc(name: str, **cols) -> int:
    with db.connect() as conn:
        loc = conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()["current_location_id"]
        code = world._next_code(conn, "npcs", "")
        fields = {"code": code, "location_id": int(loc), "name": name, **cols}
        names = ", ".join(fields)
        conn.execute(f"INSERT INTO npcs ({names}) VALUES ({', '.join('?' for _ in fields)})", list(fields.values()))
        return int(conn.execute("SELECT id FROM npcs WHERE name = ?", (name,)).fetchone()["id"])


def _npc(npc_id: int) -> dict:
    with db.connect() as conn:
        return dict(conn.execute("SELECT * FROM npcs WHERE id = ?", (npc_id,)).fetchone())


def _setting(key: str):
    with db.connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


_SCENE = " ".join(["The yard is quiet and the rain keeps falling on the stones."] * 12)


class TestQuestTimersAreInsideTheRecord(unittest.TestCase):
    def test_rewind_restores_the_timer(self):
        _fresh_world()
        _play(_SCENE)
        quest_id = _timed_quest(3)
        self.assertEqual(_remaining(quest_id), (3, "active"))
        _play(_SCENE)
        self.assertEqual(_remaining(quest_id), (2, "active"))
        world.rewind_last_turn()
        self.assertEqual(_remaining(quest_id), (3, "active"), "the rewound turn's tick must be undone")

    def test_regenerate_ticks_once_not_twice(self):
        _fresh_world()
        _play(_SCENE)
        quest_id = _timed_quest(3)
        _play(_SCENE)
        self.assertEqual(_remaining(quest_id), (2, "active"))
        _regenerate(_SCENE)
        self.assertEqual(_remaining(quest_id), (2, "active"), "one regenerate must not cost a second tick")

    def test_a_regenerate_cannot_fail_a_quest_early(self):
        _fresh_world()
        _play(_SCENE)
        quest_id = _timed_quest(2)
        _play(_SCENE)
        self.assertEqual(_remaining(quest_id), (1, "active"))
        _regenerate(_SCENE)
        self.assertEqual(_remaining(quest_id), (1, "active"))

    def test_quest_created_inside_the_turn_is_removed(self):
        _fresh_world()
        _play(_SCENE)
        with db.connect() as conn:
            before = int(conn.execute("SELECT COUNT(*) FROM quests").fetchone()[0])
        # A quest minted during the turn (after the snapshot) is gone after a rewind.
        original = world._write_turn_summary

        def write_and_mint(conn, *args, **kwargs):
            quests.create_quest(conn, title="Posted mid-turn", steps=[{"title": "x"}])
            return original(conn, *args, **kwargs)

        with mock.patch.object(world, "_write_turn_summary", side_effect=write_and_mint):
            _play(_SCENE)
        with db.connect() as conn:
            self.assertEqual(int(conn.execute("SELECT COUNT(*) FROM quests").fetchone()[0]), before + 1)
        world.rewind_last_turn()
        with db.connect() as conn:
            self.assertEqual(int(conn.execute("SELECT COUNT(*) FROM quests").fetchone()[0]), before)

    def test_quest_clocks_round_trip(self):
        _fresh_world()
        _play(_SCENE)
        with db.connect() as conn:
            local_intel.ensure_quest_clock_table(conn)
            conn.execute(
                "INSERT OR REPLACE INTO quest_clocks (subject_key, offers, chance, phase, phase_day, quest_id, last_day) "
                "VALUES ('npc:3', 1, 5, 'idle', 2, 0, 2)"
            )
        _play(_SCENE)
        with db.connect() as conn:
            conn.execute("UPDATE quest_clocks SET last_day = 9, phase = 'offered' WHERE subject_key = 'npc:3'")
        world.rewind_last_turn()
        with db.connect() as conn:
            row = conn.execute("SELECT last_day, phase FROM quest_clocks WHERE subject_key = 'npc:3'").fetchone()
        self.assertEqual((int(row["last_day"]), row["phase"]), (2, "idle"))


class TestPreTurnWritesAreInsideTheRecord(unittest.TestCase):
    def test_pronoun_pin_is_undone_by_rewind_and_re_inferred(self):
        _fresh_world()
        _play(_SCENE)
        mara = _add_npc("Mara")
        self.assertEqual(_npc(mara)["pronouns"], "")
        _play("Mara steps out of the rain. She nods once and says nothing. " + _SCENE)
        self.assertEqual(_npc(mara)["pronouns"], "she")
        world.rewind_last_turn()
        self.assertEqual(_npc(mara)["pronouns"], "", "the discarded narration's pin must not survive the rewind")
        _play("Mara steps out of the rain. He nods once and says nothing. " + _SCENE)
        self.assertEqual(_npc(mara)["pronouns"], "he")

    def test_regenerate_re_infers_from_the_new_narration(self):
        _fresh_world()
        _play(_SCENE)
        mara = _add_npc("Mara")
        _play("Mara steps out of the rain. She nods once and says nothing. " + _SCENE)
        self.assertEqual(_npc(mara)["pronouns"], "she")
        _regenerate("Mara steps out of the rain. He nods once and says nothing. " + _SCENE)
        self.assertEqual(_npc(mara)["pronouns"], "he")

    def test_social_writes_captured_before_the_turn_are_restored(self):
        """The social check's writes travel to the snapshot as `_snapshot_rows`."""
        _fresh_world()
        _play(_SCENE)
        npc_id = _add_npc("Tam", trust=10, attitude="neutral")
        self.assertIsNone(_setting("last_social"))
        pre_rows: dict = {}
        with db.connect() as conn:
            code = _npc(npc_id)["code"]
            loc = int(conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()["current_location_id"])
            world._capture_pre_turn_rows(conn, pre_rows, npc_code=code, location_id=loc, setting_keys=("last_social",))
            # What play_turn's social check does next:
            conn.execute("UPDATE npcs SET attitude = 'warm' WHERE id = ?", (npc_id,))
            world.adjust_npc_trust(conn, code, 3, reason="social_success")
            world._set_setting(conn, "last_social", {"npc_code": code, "attitude": "warm"})
        self.assertEqual(_npc(npc_id)["trust"], 13)
        self.assertIsNotNone(_setting("last_social"))
        turn = _turn(_SCENE)
        turn["_snapshot_rows"] = pre_rows
        world.apply_turn(turn, player_input="I greet Tam")
        world.rewind_last_turn()
        after = _npc(npc_id)
        self.assertEqual((after["trust"], after["attitude"]), (10, "neutral"))
        self.assertIsNone(_setting("last_social"), "a setting the turn created is gone after the rewind")

    def test_active_scene_written_by_the_turn_is_undone(self):
        _fresh_world()
        _play(_SCENE)
        self.assertIsNone(_setting("active_scene"))
        turn = _turn(_SCENE)
        turn["scene_cast"] = {"present": ["B"], "interacting": ["B"], "off": [], "keywords": ["gate"]}
        world.apply_turn(turn, player_input="I approach the gate")
        self.assertIn("B", json.loads(_setting("active_scene")).get("interacting"))
        world.rewind_last_turn()
        self.assertIsNone(_setting("active_scene"))

    def test_old_snapshot_without_quest_ids_keeps_quests(self):
        """A record written before the quest tables joined it must not wipe them."""
        _fresh_world()
        _play(_SCENE)
        quest_id = _timed_quest(3)
        _play(_SCENE)
        with db.connect() as conn:
            row = conn.execute("SELECT id, snapshot FROM turn_snapshots ORDER BY id DESC LIMIT 1").fetchone()
            snap = json.loads(row["snapshot"])
            for key in ("quests", "quest_steps", "quest_clocks"):
                snap["rows"].pop(key, None)
                snap["max_ids"].pop(key, None)
            conn.execute("UPDATE turn_snapshots SET snapshot = ? WHERE id = ?", (json.dumps(snap), int(row["id"])))
        world.rewind_last_turn()
        self.assertIsNotNone(_remaining(quest_id))


if __name__ == "__main__":
    unittest.main()
