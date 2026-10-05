"""Playtest #24, #25, #27: what the game-2 save (auto-ab564b3c-t00004) carried.

#24  Aria's summary read "Introduced this turn: Aria Aria is a baker with a
     steady hand and a sharp mind.": NPC_NEW stored a placeholder as the
     summary and the first NPC_NOTE was glued on with a bare space.
#25  The save carried 75 world maps dating back to July; one was in use.
#27  Workplaces became location rows as soon as a tradesperson stood near the
     player (turn 1 "Aria's Bakery"; turn 4 a seeded weaver got "Jethand's
     Tailor"). They are planned records now, made places only when the player
     goes there, asks for one, or the story names it.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-save-audit-"))
os.environ.update(isolated_data_env(str(_TMP)))
os.environ.update(
    {
        "AI_RPG_PACK_DIR": str(_TMP / "packs"),
        "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
    }
)

from app import db, tile_world, world  # noqa: E402
from app.db import connect  # noqa: E402
from app.turn_dsl import ops_to_turn, parse_ops  # noqa: E402

LEGACY_SEED = tile_world.LEGACY_BOARD_SEED


def seed_edge() -> None:
    db.init_db()
    with connect() as conn:
        conn.execute("UPDATE player SET current_location_id = 1 WHERE id = 1")
        conn.execute("DELETE FROM npcs")
        conn.execute("DELETE FROM locations WHERE id != 1")
        conn.execute("DELETE FROM settings WHERE key IN ('active_scene', 'conversation', 'scene_thread')")
        conn.execute(
            "UPDATE locations SET name = 'Eldoria''s Edge', summary = 'A frontier village.', parent_id = 0, "
            "kind = '', settlement_size = '', keeper_npc_id = 0 WHERE id = 1"
        )


class IntroducedPlaceholder(unittest.TestCase):
    """#24."""

    def setUp(self):
        seed_edge()

    def test_npc_new_without_desc_stores_no_placeholder(self):
        turn = ops_to_turn("Aria nods.", parse_ops('NPC_NEW Aria "Aria" ROLE baker LOC L1'))
        self.assertEqual(turn["npcs"][0]["summary"], "")
        self.assertNotIn("Introduced", json.dumps(turn))

    def test_game2_new_then_note_reads_as_one_sentence(self):
        ops = 'NPC_NEW Aria "Aria" ROLE baker LOC L1\nNPC_NOTE A "Aria is a baker with a steady hand and a sharp mind."'
        turn = ops_to_turn("Aria nods.", parse_ops(ops))
        with connect() as conn:
            world._upsert_npc(conn, turn["npcs"][0])
            world._apply_index_updates(conn, turn["index_updates"])
            summary = conn.execute("SELECT summary FROM npcs WHERE name = 'Aria'").fetchone()[0]
        self.assertEqual(summary, "Aria is a baker with a steady hand and a sharp mind.")

    def test_notes_join_as_separate_sentences(self):
        self.assertEqual(world._merge_text("A baker", "She hums.", 400), "A baker. She hums.")
        self.assertEqual(world._merge_text("A baker.", "She hums.", 400), "A baker. She hums.")
        self.assertEqual(world._merge_text("", "She hums.", 400), "She hums.")
        self.assertEqual(world._merge_text("A baker.", "A baker.", 400), "A baker.")
        with connect() as conn:
            conn.execute("INSERT INTO npcs (code, location_id, name, role, summary) VALUES ('A', 1, 'Aria', 'baker', 'Kneads dough')")
            world._upsert_npc(conn, {"code": "A", "name": "Aria", "location": "L1", "summary": "Owes the miller."})
            summary = conn.execute("SELECT summary FROM npcs WHERE code = 'A'").fetchone()[0]
        self.assertEqual(summary, "Kneads dough. Owes the miller.")

    def test_stored_rows_are_repaired_on_load(self):
        self.assertEqual(
            db.strip_introduced_prefix(
                "Introduced this turn: Aria Aria is a baker with a steady hand and a sharp mind.", "Aria"
            ),
            "Aria is a baker with a steady hand and a sharp mind.",
        )
        self.assertEqual(db.strip_introduced_prefix("Introduced this turn: Elara", "Elara"), "")
        self.assertEqual(db.strip_introduced_prefix("A baker.", "Aria"), "A baker.")
        export = world.export_world()
        export["tables"]["npcs"] = [
            {"id": 1, "code": "A", "location_id": 1, "name": "Aria", "role": "baker",
             "summary": "Introduced this turn: Aria Aria is a baker with a steady hand and a sharp mind."},
            {"id": 2, "code": "B", "location_id": 1, "name": "Elara", "role": "local",
             "summary": "Introduced this turn: Elara"},
        ]
        world.import_world(export)
        with connect() as conn:
            rows = dict(conn.execute("SELECT name, summary FROM npcs").fetchall())
        self.assertEqual(rows["Aria"], "Aria is a baker with a steady hand and a sharp mind.")
        self.assertEqual(rows["Elara"], "")


def _add_map(conn, map_id: str, *, seed: int = 7, size: int = 32, created: str = "2026-07-19 11:43:45") -> None:
    conn.execute(
        "INSERT INTO world_maps (id, seed, width, height, tiles_json, created_at) VALUES (?, ?, ?, ?, '[]', ?)",
        (map_id, seed, size, size, created),
    )


class MapsArePruned(unittest.TestCase):
    """#25."""

    def setUp(self):
        db.init_db()
        with connect() as conn:
            conn.execute("DELETE FROM world_maps")
            for n in range(74):
                _add_map(conn, f"map-{n}-old")
            _add_map(conn, "map-legacy", seed=LEGACY_SEED, size=36)
            _add_map(conn, "world-1000494135-3567a8c1", size=16383, created="2026-10-04 22:33:41")
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES ('active_world_map_id', 'world-1000494135-3567a8c1')"
            )

    def test_save_exports_only_the_active_map(self):
        rows = world.export_world()["tables"]["world_maps"]
        self.assertEqual([r["id"] for r in rows], ["world-1000494135-3567a8c1"])

    def test_without_an_active_map_the_save_keeps_every_map(self):
        with connect() as conn:
            conn.execute("DELETE FROM settings WHERE key = 'active_world_map_id'")
        self.assertEqual(len(world.export_world()["tables"]["world_maps"]), 76)

    def test_new_game_drops_maps_this_campaign_does_not_use(self):
        world.start_playthrough({"player_name": "Ash", "start_location": "Low Gate", "special_ability_origin": "none"})
        with connect() as conn:
            ids = sorted(r[0] for r in conn.execute("SELECT id FROM world_maps"))
        self.assertEqual(ids, ["map-legacy", "world-1000494135-3567a8c1"])

    def test_loading_an_old_save_with_many_maps_still_works(self):
        old = world.export_world()
        old["tables"]["world_maps"] = [
            {"id": f"map-{n}-slot", "seed": n, "width": 32, "height": 32, "tiles_json": "[]"} for n in range(75)
        ]
        old["tables"]["world_maps"].append({"id": "map-legacy", "seed": LEGACY_SEED, "width": 36, "height": 36, "tiles_json": "[]"})
        old["tables"]["settings"] = [
            row for row in old["tables"]["settings"] if row["key"] != "active_world_map_id"
        ] + [{"key": "active_world_map_id", "value": "map-3-slot"}]
        world.import_world(old)
        with connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM world_maps").fetchone()[0]
        self.assertEqual(count, 76)
        self.assertEqual(tile_world.get_map(None)["id"], "map-3-slot")
        # Re-saving it carries one map.
        self.assertEqual([r["id"] for r in world.export_world()["tables"]["world_maps"]], ["map-3-slot"])

    def test_loading_a_new_save_keeps_the_legacy_board(self):
        new = world.export_world()
        self.assertNotIn("map-legacy", [r["id"] for r in new["tables"]["world_maps"]])
        world.import_world(new)
        with connect() as conn:
            ids = sorted(r[0] for r in conn.execute("SELECT id FROM world_maps"))
        self.assertEqual(ids, ["map-legacy", "world-1000494135-3567a8c1"])

    def test_saved_slots_carry_their_own_maps(self):
        world.save_campaign_slot("before-new-game")
        world.start_playthrough({"player_name": "Ash", "start_location": "Low Gate", "special_ability_origin": "none"})
        with connect() as conn:
            conn.execute("DELETE FROM world_maps WHERE id = 'world-1000494135-3567a8c1'")
        world.load_campaign_slot("before-new-game")
        self.assertEqual(tile_world.get_map(None)["id"], "world-1000494135-3567a8c1")


class WorkplacesArePlanned(unittest.TestCase):
    """#27."""

    def setUp(self):
        seed_edge()
        with connect() as conn:
            for code, name, role in (("A", "Aria", "baker"), ("B", "Jethand", "weaver"), ("C", "Hearthbin", "message runner")):
                conn.execute("INSERT INTO npcs (code, location_id, name, role) VALUES (?, 1, ?, ?)", (code, name, role))

    def _names(self) -> list[str]:
        with connect() as conn:
            return [r[0] for r in conn.execute("SELECT name FROM locations ORDER BY id")]

    def test_a_tradesperson_nearby_makes_no_place(self):
        with connect() as conn:
            world._ensure_workplaces_here(conn)
            plans = {
                r["name"]: json.loads(r["workplace_plan"] or "{}")
                for r in conn.execute("SELECT name, workplace_plan FROM npcs")
            }
        self.assertEqual(self._names(), ["Eldoria's Edge"])
        self.assertEqual(plans["Aria"], {"kind": "bakery", "name": "Aria's Bakery", "parent_id": 1})
        self.assertEqual(plans["Jethand"]["name"], "Jethand's Tailor")
        self.assertEqual(plans["Hearthbin"], {})

    def test_the_plan_still_tells_the_prompts_whose_place_it_is(self):
        from app.prompts import _visible_world

        with connect() as conn:
            world._ensure_workplaces_here(conn)
        state = world.get_state(include_hidden=True)
        context = world.build_prompt_context(state, "look around")
        people = {p["name"]: p for p in _visible_world(context, "look around")["current_location"]["people"]}
        self.assertEqual(people["Aria"].get("works_at"), "Aria's Bakery")
        self.assertNotIn("works_here", people["Aria"])
        self.assertNotIn("workplace_plan", json.dumps(state))

    def test_the_story_naming_it_makes_it_a_place(self):
        with connect() as conn:
            world._ensure_workplaces_here(conn)
            made = world._realize_named_workplaces(conn, "I chat with Aria", "Aria wipes flour off her hands and mentions Aria's Bakery opens at dawn.")
            row = conn.execute("SELECT * FROM locations WHERE name = ?", ("Aria's Bakery",)).fetchone()
            aria = conn.execute("SELECT id, workplace_id, workplace_plan FROM npcs WHERE name = 'Aria'").fetchone()
        self.assertEqual(made, ["Aria's Bakery"])
        self.assertEqual((row["parent_id"], row["kind"], row["keeper_npc_id"]), (1, "bakery", aria["id"]))
        self.assertEqual((aria["workplace_id"], aria["workplace_plan"]), (row["id"], ""))
        self.assertNotIn("Jethand's Tailor", self._names())

    def test_the_player_asking_for_the_trade_makes_it_a_place(self):
        with connect() as conn:
            world._ensure_workplaces_here(conn)
            made = world._realize_named_workplaces(conn, "I head over to the bakery for bread", "")
        self.assertEqual(made, ["Aria's Bakery"])
        self.assertNotIn("Jethand's Tailor", self._names())

    def test_chat_that_never_names_it_makes_nothing(self):
        with connect() as conn:
            world._ensure_workplaces_here(conn)
            made = world._realize_named_workplaces(conn, "I ask Aria about the road north", "Aria shrugs and points north.")
        self.assertEqual(made, [])
        self.assertEqual(self._names(), ["Eldoria's Edge"])

    def test_a_move_there_through_play_turn_lands_inside(self):
        from unittest import mock

        with connect() as conn:
            world._ensure_workplaces_here(conn)
        prose = "You follow Aria down the lane and step into Aria's Bakery, warm with the smell of bread."

        def fake_generate(context, model_input):
            return {
                "scene_plan": {"goal": "go", "focus_points": []},
                "narration_segments": [{"label": "scene", "text": prose}],
                "narration": prose,
                "player": {"move_to_location": "Aria's Bakery"},
                "self_check": {"passed": True, "issues_found": [], "corrections_made": []},
                "turn_summary": "the player goes to the bakery",
                "scene_focus": "action",
            }

        with mock.patch.object(world, "generate_turn", side_effect=fake_generate):
            state = world.play_turn("I go to Aria's bakery")["state"]
        self.assertEqual(state["current_location"]["name"], "Aria's Bakery")
        self.assertEqual(self._names().count("Aria's Bakery"), 1)
        self.assertNotIn("Jethand's Tailor", self._names())


if __name__ == "__main__":
    unittest.main()
