"""Game-start presets read campaign slot files, never the live database.

A previous game shows up as how it began: the stored setup form, or the
opening journal line when that form was never saved. Run:

    python -m unittest tests.test_game_start_presets
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import world


class GameStartPresetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="morkyn-game-starts-"))
        patcher = mock.patch.dict(os.environ, {"AI_RPG_CAMPAIGN_SLOTS": str(self.tmp)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def make_slot(self, name, *, campaign_id, turn, saved_at, player_name="Mara", world_data=None):
        slot = self.tmp / name
        slot.mkdir(parents=True, exist_ok=True)
        (slot / "world.json").write_text(json.dumps(world_data or {"tables": {}}), encoding="utf-8")
        meta = {
            "slot": name,
            "campaign_id": campaign_id,
            "turn": turn,
            "saved_at": saved_at,
            "player_name": player_name,
        }
        (slot / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
        return slot

    def test_journal_line_is_the_opening_and_one_row_per_game(self):
        opening = {"player_name": "Mara", "difficulty": "hard", "special_abilities": [{"name": "Hearth Spark"}]}
        journal = {
            "tables": {
                "journal": [
                    {"kind": "setup", "turn": 0, "content": "Playthrough started: " + json.dumps(opening)},
                    {"kind": "narration", "turn": 9, "content": "Later, in the city."},
                ]
            }
        }
        self.make_slot(
            "auto-aaaa1111-t0",
            campaign_id="aaaa1111",
            turn=0,
            saved_at="2026-09-01T00:00:00+00:00",
            world_data=journal,
        )
        self.make_slot(
            "auto-aaaa1111-t9",
            campaign_id="aaaa1111",
            turn=9,
            saved_at="2026-09-02T00:00:00+00:00",
            player_name="Mara",
            world_data={"tables": {"journal": [{"kind": "narration", "content": "mid game"}]}},
        )
        rows = world.list_game_start_presets()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], "aaaa1111")
        self.assertEqual(rows[0]["slot"], "auto-aaaa1111-t0")
        self.assertIn("Mara", rows[0]["label"])
        detail = world.get_game_start_preset("aaaa1111")
        self.assertEqual(detail["options"]["player_name"], "Mara")
        self.assertEqual(detail["options"]["special_abilities"][0]["name"], "Hearth Spark")
        self.assertNotIn("form", detail)
        cached = json.loads((self.tmp / "auto-aaaa1111-t0" / "start.json").read_text(encoding="utf-8"))
        self.assertEqual(cached["options"]["difficulty"], "hard")

    def test_saved_form_is_how_the_game_started(self):
        form = {
            "format": "ai-rpg-setup-settings-v1",
            "controls": [{"name": "player_name", "value": "Ivo"}],
            "abilities": [{"name": "Glass Step"}],
        }
        slot = self.make_slot(
            "auto-bbbb2222-t4",
            campaign_id="bbbb2222",
            turn=4,
            saved_at="2026-09-03T12:00:00+00:00",
            player_name="Ivo",
        )
        (slot / "start.json").write_text(
            json.dumps({"campaign_id": "bbbb2222", "slot": "auto-bbbb2222-t4", "player_name": "Ivo", "saved_at": "2026-09-01T00:00:00+00:00", "form": form}),
            encoding="utf-8",
        )
        rows = world.list_game_start_presets()
        self.assertEqual(len(rows), 1)
        detail = world.get_game_start_preset("bbbb2222")
        self.assertEqual(detail["form"]["abilities"][0]["name"], "Glass Step")
        self.assertEqual(detail["form"]["controls"][0]["value"], "Ivo")

    def test_form_wins_over_the_journal_line(self):
        found = world._game_start_from_export({
            "tables": {
                "settings": [{
                    "key": "game_start_form",
                    "value": json.dumps({"controls": [{"name": "difficulty", "value": "brutal"}]}),
                }],
                "journal": [{
                    "kind": "setup",
                    "content": 'Playthrough started: {"player_name": "Old"}',
                }],
            }
        })
        self.assertEqual(found["form"]["controls"][0]["value"], "brutal")
        self.assertNotIn("options", found)

    def test_a_bad_id_is_refused(self):
        self.assertIsNone(world.get_game_start_preset("../world"))
        self.assertIsNone(world.get_game_start_preset("missing-game"))
