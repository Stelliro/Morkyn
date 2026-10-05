"""
Live gate batch 4 (real Qwen3 8B, the player's launcher env): who keeps a
venue the player walks into, and whose name an NPC code carries.

Every input, narration and DB row here is copied from the live run
(smoke/batch4_r1, g1_/g2_ turn 5 payloads and t4/t5 DB dumps):

  G2 T5 "go inside the first trading post": the venue was made and entered,
    but keeper_npc_id = Nesta Grisham, the carter companion who walked in
    with the player (movement.settled.moved_in = [Nesta]); the bearded trader
    the prose put behind the counter was never seeded, because the companion
    who had just walked in counted as the face the prose showed.
  G1 T5 "go into the nearest smithy": keeper_npc_id = Iseult Thatcher, the
    water carrier on the scene thread. The model's npcs held
    {"code": "C", "name": "Nichola Furlong", "role": "smith"}; C was already
    Linnet Tapley (cooper, L1), and the DB kept "Linnet Tapley" with role
    smith and moved her into the cookshop: the model's new name was dropped.
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
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-live-batch4-keepers-"))
os.environ.update(isolated_data_env(str(_TMP)))
os.environ.update(
    {
        "AI_RPG_PACK_DIR": str(_TMP / "packs"),
        "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
        "AI_RPG_IDEA_BANK": str(_TMP / "idea_bank"),
        "AI_RPG_LAUNCHER_PREFS": str(_TMP / "launcher_prefs.json"),
    }
)
LAUNCHER_ENV = {
    "AI_RPG_NARRATION_PIPELINE": "1",
    "AI_RPG_NARRATION_PIPELINE_CONSOLIDATE": "1",
    "AI_RPG_FAST_VERIFICATION": "1",
    "AI_RPG_DSL_SKIP_VERIFY": "1",
    "AI_RPG_DRAFT_MODE": "dsl",
}
_launcher_patch = mock.patch.dict(os.environ, {**LAUNCHER_ENV, "AI_RPG_DB": os.environ["AI_RPG_DB"]})


def setUpModule():
    _launcher_patch.start()


def tearDownModule():
    _launcher_patch.stop()


from app import db, world  # noqa: E402
from app.db import connect  # noqa: E402

G2T5_INPUT = "I give up on Elias for now, walk back to the city's edge and go inside the first trading post to see what they sell."
G2T5_NARRATION = (
    "You turn away from Elias Thorn [[B]], the watcher with the sharp eyes and sharper questions, and start heading "
    "east toward the city's edge, the weight of your pack a constant reminder of the journey you've come from. The "
    "path is clear, the terrain soft underfoot, and the sky a brilliant blue with no hint of storm, though the breeze "
    "carries the faintest trace of dampness from the woods.\n\nThe first trading post appears at the edge of the "
    "clearing, its wooden walls weathered but sturdy, the sign above it faded but still legible. You step inside, the "
    "door creaking open to reveal a warm, smoky interior filled with the smell of dried herbs, cured meat, and the "
    "faint tang of salt from the sea. The trader behind the counter is a broad-shouldered man with a thick beard and "
    "a look of practiced indifference, his fingers stained with ink from the ledger he keeps.\n\nHe doesn’t look "
    "up as you step inside, the door creaking shut behind you, but the faint rustle of parchment and the slow clink "
    "of metal from the shelves suggest he’s already aware of your presence.\n\nHe doesn’t ask who you are or "
    "why you’ve come, but his eyes flicker with curiosity as he scans the goods on his shelves—bundles of "
    "dried fish, jars of pickled vegetables, and a stack of cloth wrapped in oilskin."
)
G2_THREAD = {
    "version": 1, "doing": "follow Elias Thorn", "target": "Elias Thorn", "target_code": "B",
    "with": [{"code": "A", "name": "Nesta Grisham"}], "quest": {}, "source": "player",
    "started_turn": 5, "touched_turn": 5, "where": "Clearing at Forest's Edge",
}

G1T5_INPUT = "I back away from the archway and go into the nearest smithy to ask what that sigil means."
G1T5_NARRATION = (
    "You step away from the archway and find yourself in a small smithy, the clang of hammer on metal echoing from "
    "within. The shop is modest, its wooden frame weathered but sturdy, with a sign above the door that reads "
    "“Furlong's Cookshop.” Inside, the smell of hot iron and burning wood fills the space, and a single worker "
    "is bent over a forge, their hands moving with practiced precision.\n\nTheir name is Iseult Thatcher [[B]], and "
    "they are the water carrier who has been watching you with an expression that is both wary and curious. "
    "“You're not the first to follow that path,” she says, her tone measured, “but you may be the "
    "last.” She gestures toward the sigil you've been studying, the shape of a stormcloud etched into the wooden "
    "frame of the archway.\n\nAs she speaks, the forge behind her flickers with a sudden burst of heat, and the sound "
    "of metal being shaped grows louder. You notice that the shop is not empty—there are other people in the "
    "background, their faces obscured by the haze of the forge's heat, but their presence is unmistakable.\n\nYou "
    "step into the smithy, the heat of the forge pressing close, and Iseult Thatcher [[B]] watches you with that same "
    "careful intensity, her fingers still moving over the metal as if she’s shaping more than mere iron."
)
G1T5_NPCS = [
    {"code": "B", "name": "Iseult Thatcher", "race": "human", "location": "Furlong's Cookshop",
     "role": "water carrier", "summary": "", "attitude": "cautious"},
    {"code": "C", "name": "Nichola Furlong", "race": "human", "location": "Furlong's Cookshop",
     "role": "smith", "summary": "", "attitude": "cautious"},
]
G1_THREAD = {
    "version": 1, "doing": "follow the cloaked watcher", "target": "the cloaked watcher", "target_code": "",
    "with": [{"code": "B", "name": "Iseult Thatcher"}], "quest": {}, "source": "player",
    "started_turn": 5, "touched_turn": 5, "where": "Archway of the Stormcallers",
}

_SEEDS = 0


def seed_world(places, npcs, here: int, thread: dict, options: dict) -> None:
    global _SEEDS
    _SEEDS += 1
    os.environ["AI_RPG_DB"] = str(_TMP / f"world_{_SEEDS}.db")
    db.init_db()
    with connect() as conn:
        conn.execute("DELETE FROM npcs")
        conn.execute("DELETE FROM settings WHERE key IN ('active_scene', 'conversation', 'scene_thread')")
        for loc_id, name in places:
            if conn.execute("SELECT 1 FROM locations WHERE id = ?", (loc_id,)).fetchone():
                conn.execute(
                    "UPDATE locations SET name = ?, code = ?, parent_id = 0, kind = '', keeper_npc_id = 0 WHERE id = ?",
                    (name, f"L{loc_id}", loc_id),
                )
            else:
                conn.execute(
                    "INSERT INTO locations (id, code, name, summary) VALUES (?, ?, ?, '')", (loc_id, f"L{loc_id}", name)
                )
        for code, loc_id, name, role in npcs:
            conn.execute(
                "INSERT INTO npcs (code, location_id, name, role, summary) VALUES (?, ?, ?, ?, '')",
                (code, loc_id, name, role),
            )
        conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (here,))
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('scene_thread', ?)", (json.dumps(thread),))
        row = conn.execute("SELECT value FROM settings WHERE key = 'playthrough_options'").fetchone()
        merged = {**(json.loads(row[0]) if row else {}), **options}
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('playthrough_options', ?)", (json.dumps(merged),)
        )


def fake_turn(narration: str, **extra):
    def fake_generate(context, model_input):
        return {
            "scene_plan": {"goal": "go on", "focus_points": []},
            "narration_segments": [{"label": "scene", "text": narration}],
            "narration": narration,
            "player": {},
            "self_check": {"passed": True, "issues_found": [], "corrections_made": []},
            "turn_summary": "the player goes on",
            "scene_focus": "action",
            **extra,
        }

    return fake_generate


def play(player_input: str, narration: str, **extra) -> dict:
    with mock.patch.object(world, "generate_turn", side_effect=fake_turn(narration, **extra)):
        return world.play_turn(player_input)


def row(sql: str, *args) -> dict:
    with connect() as conn:
        found = conn.execute(sql, args).fetchone()
    return dict(found) if found else {}


def player_location() -> int:
    return int(row("SELECT current_location_id FROM player WHERE id = 1")["current_location_id"])


class CompanionIsNeverTheKeeper(unittest.TestCase):
    def test_live_g2_first_trading_post(self):
        seed_world(
            [(1, "The Empty Lot"), (2, "Clearing at Forest's Edge")],
            [
                ("A", 2, "Nesta Grisham", "carter"),
                ("B", 2, "Elias Thorn", "watcher"),
                ("C", 2, "Isolde Saxby", "watcher"),
                ("D", 2, "Mara Vey", "hunter"),
            ],
            here=2,
            thread=G2_THREAD,
            options={"world_style": "frontier dark fantasy", "tech_level": "medieval"},
        )
        play(G2T5_INPUT, G2T5_NARRATION, player={"move_to_location": "The First Trading Post"})
        venue = row("SELECT * FROM locations WHERE name = ? COLLATE NOCASE", "The First Trading Post")
        self.assertTrue(venue, "the trading post was not made")
        self.assertEqual(player_location(), int(venue["id"]))
        nesta = row("SELECT * FROM npcs WHERE name = 'Nesta Grisham'")
        self.assertNotEqual(int(venue["keeper_npc_id"] or 0), int(nesta["id"]), "the carter companion keeps the shop")
        self.assertEqual(int(nesta["workplace_id"] or 0), 0, "the carter's workplace became the trading post")
        # The trader the prose shows behind the counter is a real person there, and keeps it.
        keeper = row("SELECT * FROM npcs WHERE id = ?", int(venue["keeper_npc_id"] or 0))
        self.assertTrue(keeper, "nobody keeps the trading post")
        self.assertEqual(int(keeper["location_id"]), int(venue["id"]))

    def test_live_g1_cookshop(self):
        seed_world(
            [(1, "Threshold of the Stormcallers' First Breath"), (2, "Archway of the Stormcallers")],
            [
                ("A", 1, "Rhys Eastlake", "candle maker"),
                ("B", 2, "Iseult Thatcher", "water carrier"),
                ("C", 1, "Linnet Tapley", "cooper"),
            ],
            here=2,
            thread=G1_THREAD,
            options={"world_style": "Fantasy progression RPG", "tech_level": "medieval"},
        )
        play(
            G1T5_INPUT,
            G1T5_NARRATION,
            player={"move_to_location": "Furlong's Cookshop"},
            npcs=[dict(n) for n in G1T5_NPCS],
        )
        venue = row("SELECT * FROM locations WHERE name = ? COLLATE NOCASE", "Furlong's Cookshop")
        self.assertTrue(venue)
        iseult = row("SELECT * FROM npcs WHERE name = 'Iseult Thatcher'")
        self.assertNotEqual(int(venue["keeper_npc_id"] or 0), int(iseult["id"]), "the water carrier keeps the shop")
        nichola = row("SELECT * FROM npcs WHERE name = 'Nichola Furlong'")
        self.assertTrue(nichola, "the model's new smith was renamed into Linnet")
        self.assertEqual(int(venue["keeper_npc_id"] or 0), int(nichola["id"]))


class ACodeDoesNotRenameSomeoneElse(unittest.TestCase):
    def test_live_c_is_linnet_not_nichola(self):
        seed_world(
            [(1, "Threshold of the Stormcallers' First Breath"), (2, "Archway of the Stormcallers")],
            [("C", 1, "Linnet Tapley", "cooper")],
            here=2,
            thread=G1_THREAD,
            options={"tech_level": "medieval"},
        )
        entry = dict(G1T5_NPCS[1], location="Archway of the Stormcallers")
        with connect() as conn:
            new_id = world._upsert_npc(conn, entry)
        linnet = row("SELECT * FROM npcs WHERE name = 'Linnet Tapley'")
        self.assertEqual((linnet["code"], linnet["role"], int(linnet["location_id"])), ("C", "cooper", 1))
        nichola = row("SELECT * FROM npcs WHERE id = ?", new_id)
        self.assertEqual((nichola["name"], nichola["role"]), ("Nichola Furlong", "smith"))
        self.assertNotEqual(nichola["code"], "C")
        self.assertEqual(entry["code"], nichola["code"], "the turn's npc entry still points at Linnet's code")

    def test_same_person_by_code_still_updates(self):
        seed_world([(1, "Threshold")], [("C", 1, "Linnet Tapley", "cooper")], here=1, thread={}, options={})
        with connect() as conn:
            same = world._upsert_npc(conn, {"code": "C", "name": "Linnet", "role": "cooper", "location": "Threshold"})
        self.assertEqual(int(row("SELECT id FROM npcs WHERE code = 'C'")["id"]), same)
        with connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM npcs").fetchone()[0]
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
