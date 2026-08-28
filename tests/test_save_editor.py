"""
Editing a save's contents, for a person in the browser and for an agent.

Neither could before. Of 79 mutating endpoints none touched a save's contents,
so trimming one item's quantity from 3 to 1 meant a bespoke script, a hand-made
backup and a verification pass. The blob store made it harder still: opening
world.json now shows {"__blob__": ...} where the map used to be.
"""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import world
from app.save_editor import BLOCKED_TABLES, SaveEditError, apply_edits, read_save

SEED_SAVE = {
    "format": "ai-rpg-world-v1",
    "tables": {
        "player": [{"id": 1, "name": "Kael Veyra", "level": 2, "gold": 14}],
        "inventory": [
            {"id": 1, "code": "I1", "name": "frayed sailor coat", "quantity": 1},
            {"id": 2, "code": "I4", "name": "single seed in hand", "quantity": 3},
        ],
        "locations": [{"id": 1, "code": "L1", "name": "Cragwatch Barracks Gate"}],
        "world_maps": [{"id": "map-1", "tiles_json": "x" * (world.BLOB_MIN_BYTES + 5)}],
        "settings": [{"key": "player_portrait", "value": "y" * (world.BLOB_MIN_BYTES + 5)}],
    },
}


class SaveEditorTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="morkyn-edit-"))
        patcher = mock.patch.dict(os.environ, {"AI_RPG_CAMPAIGN_SLOTS": str(self.tmp)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.slot = "Kael_Veyra"
        slot_dir = self.tmp / self.slot
        slot_dir.mkdir(parents=True)
        stored = world.externalise_blobs(json.loads(json.dumps(SEED_SAVE)))
        (slot_dir / "world.json").write_text(json.dumps(stored, indent=2), encoding="utf-8")
        (slot_dir / "metadata.json").write_text(
            json.dumps({"slot": self.slot, "player_name": "Kael Veyra", "turn": 2}), encoding="utf-8"
        )

    def rows(self, table="inventory"):
        return read_save(self.slot)["tables"][table]

    def seed_qty(self):
        return next(r["quantity"] for r in self.rows() if r["code"] == "I4")


class ReadTests(SaveEditorTestCase):
    def test_returns_the_editable_tables(self):
        data = read_save(self.slot)
        self.assertIn("inventory", data["tables"])
        self.assertIn("player", data["tables"])
        self.assertEqual(data["metadata"]["player_name"], "Kael Veyra")

    def test_blob_references_are_resolved_away_for_the_caller(self):
        """Nobody editing a save should ever see a hash where a value belongs."""
        self.assertNotIn(world.BLOB_REF_KEY, json.dumps(read_save(self.slot)))

    def test_generated_tables_are_named_not_silently_dropped(self):
        data = read_save(self.slot)
        self.assertNotIn("world_maps", data["tables"])
        names = {entry["table"] for entry in data["blocked"]}
        self.assertEqual(names, set(BLOCKED_TABLES))
        for entry in data["blocked"]:
            self.assertTrue(entry["reason"], "a blocked table must say why")

    def test_reports_columns_so_a_caller_can_build_a_form(self):
        self.assertEqual(
            read_save(self.slot)["columns"]["inventory"], ["id", "code", "name", "quantity"]
        )

    def test_a_missing_save_is_a_clear_error(self):
        with self.assertRaises(SaveEditError) as caught:
            read_save("no_such_save")
        self.assertIn("not found", str(caught.exception))


class EditTests(SaveEditorTestCase):
    def test_the_seed_case_end_to_end(self):
        report = apply_edits(
            self.slot, [{"table": "inventory", "where": {"code": "I4"}, "set": {"quantity": 1}}]
        )
        self.assertEqual(report["rows_changed"], 1)
        self.assertEqual(self.seed_qty(), 1)

    def test_a_backup_is_written_before_the_change(self):
        report = apply_edits(
            self.slot, [{"table": "inventory", "where": {"code": "I4"}, "set": {"quantity": 1}}]
        )
        backup = self.tmp / self.slot / report["backup"]
        self.assertTrue(backup.exists())
        restored = world.internalise_blobs(json.loads(backup.read_text(encoding="utf-8")))
        seed = next(r for r in restored["tables"]["inventory"] if r["code"] == "I4")
        self.assertEqual(seed["quantity"], 3, "the backup must hold the value before the edit")

    def test_dry_run_reports_without_writing(self):
        report = apply_edits(
            self.slot,
            [{"table": "inventory", "where": {"code": "I4"}, "set": {"quantity": 1}}],
            dry_run=True,
        )
        self.assertTrue(report["dry_run"])
        self.assertEqual(report["edits"][0]["before"], [{"quantity": 3}])
        self.assertEqual(self.seed_qty(), 3, "a dry run must change nothing on disk")
        self.assertNotIn("backup", report)

    def test_blobs_survive_an_edit(self):
        """The map and portraits must come back intact after a round trip."""
        before = read_save(self.slot)
        apply_edits(self.slot, [{"table": "player", "where": {"id": 1}, "set": {"gold": 99}}])
        stored = json.loads((self.tmp / self.slot / "world.json").read_text(encoding="utf-8"))
        restored = world.internalise_blobs(stored)
        self.assertEqual(len(restored["tables"]["world_maps"][0]["tiles_json"]), world.BLOB_MIN_BYTES + 5)
        self.assertEqual(before["tables"]["locations"], read_save(self.slot)["tables"]["locations"])

    def test_insert_and_delete(self):
        apply_edits(self.slot, [{"table": "inventory", "insert": {"code": "I9", "name": "rope", "quantity": 1}}])
        self.assertEqual(len(self.rows()), 3)
        apply_edits(self.slot, [{"table": "inventory", "where": {"code": "I9"}, "delete": True}])
        self.assertEqual(len(self.rows()), 2)

    def test_several_edits_in_one_call(self):
        apply_edits(
            self.slot,
            [
                {"table": "inventory", "where": {"code": "I4"}, "set": {"quantity": 1}},
                {"table": "player", "where": {"id": 1}, "set": {"gold": 40, "level": 3}},
            ],
        )
        self.assertEqual(self.seed_qty(), 1)
        player = self.rows("player")[0]
        self.assertEqual((player["gold"], player["level"]), (40, 3))


class RefusalTests(SaveEditorTestCase):
    def assert_unchanged(self):
        self.assertEqual(self.seed_qty(), 3)
        self.assertEqual(len(list((self.tmp / self.slot).glob("*.bak-*"))), 0)

    def test_a_where_that_matches_nothing_is_refused(self):
        with self.assertRaises(SaveEditError) as caught:
            apply_edits(self.slot, [{"table": "inventory", "where": {"code": "I99"}, "set": {"quantity": 1}}])
        self.assertIn("nothing", str(caught.exception).lower())
        self.assert_unchanged()

    def test_generated_tables_are_refused(self):
        with self.assertRaises(SaveEditError) as caught:
            apply_edits(self.slot, [{"table": "world_maps", "where": {"id": "map-1"}, "set": {"tiles_json": "x"}}])
        self.assertIn("not editable", str(caught.exception))
        self.assert_unchanged()

    def test_an_unknown_table_lists_the_known_ones(self):
        with self.assertRaises(SaveEditError) as caught:
            apply_edits(self.slot, [{"table": "invnetory", "where": {"code": "I4"}, "set": {"quantity": 1}}])
        self.assertIn("inventory", str(caught.exception), "the message should help with the typo")
        self.assert_unchanged()

    def test_a_later_bad_edit_rolls_back_the_earlier_good_one(self):
        """All or nothing: a save half-edited by a typo is worse than a refusal."""
        with self.assertRaises(SaveEditError):
            apply_edits(
                self.slot,
                [
                    {"table": "inventory", "where": {"code": "I4"}, "set": {"quantity": 1}},
                    {"table": "inventory", "where": {"code": "nope"}, "set": {"quantity": 1}},
                ],
            )
        self.assert_unchanged()

    def test_nested_values_are_refused_with_an_explanation(self):
        with self.assertRaises(SaveEditError) as caught:
            apply_edits(self.slot, [{"table": "player", "where": {"id": 1}, "set": {"stats": {"str": 3}}}])
        self.assertIn("JSON strings", str(caught.exception))
        self.assert_unchanged()

    def test_a_missing_where_is_refused_rather_than_hitting_every_row(self):
        with self.assertRaises(SaveEditError) as caught:
            apply_edits(self.slot, [{"table": "inventory", "set": {"quantity": 99}}])
        self.assertIn("where", str(caught.exception))
        self.assert_unchanged()

    def test_an_empty_edit_list_is_refused(self):
        with self.assertRaises(SaveEditError):
            apply_edits(self.slot, [])


if __name__ == "__main__":
    unittest.main()
