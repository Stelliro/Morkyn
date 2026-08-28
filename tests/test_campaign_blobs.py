"""
Large strings in a campaign save are stored once and referenced.

Measured on a real 4.89 MB save, before any of this existed:

    world_maps        3.85 MB   tiles_json, ~133 KB per row over 25 rows
    player_fullbody    705 KB   base64 character art
    player_portrait    516 KB   base64 character art
    everything else    ~25 KB   player, inventory, journal, npcs, locations

The map was byte-identical between two saves of the same character two hours
apart. Per-turn autosaves that copy it cost 49 MB per character over ten turns;
referencing it costs about a quarter of one save.
"""

import gzip
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import world


class BlobStoreTestCase(unittest.TestCase):
    """Each test gets its own slots directory; none of them touch a real save."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="morkyn-blobs-"))
        patcher = mock.patch.dict(os.environ, {"AI_RPG_CAMPAIGN_SLOTS": str(self.tmp)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def big(self, filler="x"):
        return filler * (world.BLOB_MIN_BYTES + 10)

    def write_slot(self, name, payload):
        slot = self.tmp / name
        slot.mkdir(parents=True, exist_ok=True)
        (slot / "world.json").write_text(json.dumps(payload), encoding="utf-8")
        return slot


class RoundTripTests(BlobStoreTestCase):
    def test_a_large_string_survives_the_round_trip(self):
        payload = {"tables": {"world_maps": [{"tiles_json": self.big()}]}}
        stored = world.externalise_blobs(payload)
        self.assertEqual(world.internalise_blobs(stored), payload)

    def test_small_strings_are_left_alone(self):
        payload = {"tables": {"player": [{"name": "Kael Veyra", "backstory": "short"}]}}
        self.assertEqual(world.externalise_blobs(payload), payload)

    def test_the_stored_file_no_longer_holds_the_payload(self):
        text = self.big()
        stored = world.externalise_blobs({"art": text})
        self.assertNotIn(text, json.dumps(stored))
        self.assertIn(world.BLOB_REF_KEY, json.dumps(stored))

    def test_identical_content_is_stored_once(self):
        """The point of the exercise: ten saves of one map cost one map."""
        text = self.big()
        for _ in range(10):
            world.externalise_blobs({"tiles": text})
        self.assertEqual(len(list(world.campaign_blobs_dir().rglob("*.gz"))), 1)

    def test_different_content_is_stored_separately(self):
        world.externalise_blobs({"a": self.big("a")})
        world.externalise_blobs({"b": self.big("b")})
        self.assertEqual(len(list(world.campaign_blobs_dir().rglob("*.gz"))), 2)

    def test_blobs_are_compressed_on_disk(self):
        text = self.big()
        world.externalise_blobs({"tiles": text})
        blob = next(world.campaign_blobs_dir().rglob("*.gz"))
        self.assertLess(blob.stat().st_size, len(text))
        self.assertEqual(gzip.decompress(blob.read_bytes()).decode("utf-8"), text)

    def test_structure_and_types_are_preserved(self):
        payload = {
            "format": "ai-rpg-world-v1",
            "tables": {"settings": [{"key": "player_portrait", "value": self.big()}]},
            "counts": [1, 2.5, True, None],
        }
        self.assertEqual(world.internalise_blobs(world.externalise_blobs(payload)), payload)

    def test_nested_lists_and_dicts_are_walked(self):
        payload = {"a": [{"b": [{"c": self.big()}]}]}
        self.assertEqual(world.internalise_blobs(world.externalise_blobs(payload)), payload)


class MissingBlobTests(BlobStoreTestCase):
    def test_a_missing_blob_is_a_clear_error_not_a_crash(self):
        stored = world.externalise_blobs({"tiles": self.big()})
        for blob in world.campaign_blobs_dir().rglob("*.gz"):
            blob.unlink()
        with self.assertRaises(ValueError) as caught:
            world.internalise_blobs(stored, "Kael_Veyra")
        message = str(caught.exception)
        self.assertIn("Kael_Veyra", message, "the error should name the save that broke")
        self.assertIn("missing or unreadable", message)

    def test_a_save_with_no_references_loads_unchanged(self):
        """Saves written before the blob store must keep working."""
        legacy = {"tables": {"player": [{"name": "Kael"}]}, "format": "ai-rpg-world-v1"}
        self.assertEqual(world.internalise_blobs(legacy), legacy)


class GarbageCollectionTests(BlobStoreTestCase):
    def test_unreferenced_blobs_are_removed(self):
        self.write_slot("keep", world.externalise_blobs({"tiles": self.big("a")}))
        world.externalise_blobs({"tiles": self.big("b")})  # referenced by nothing
        report = world.gc_campaign_blobs()
        self.assertEqual(report["removed"], 1)
        self.assertEqual(report["kept"], 1)
        self.assertGreater(report["freed_bytes"], 0)

    def test_a_blob_shared_by_two_saves_survives_deleting_one(self):
        shared = self.big()
        self.write_slot("one", world.externalise_blobs({"tiles": shared}))
        self.write_slot("two", world.externalise_blobs({"tiles": shared}))
        shutil.rmtree(self.tmp / "one")
        world.gc_campaign_blobs()
        self.assertEqual(len(list(world.campaign_blobs_dir().rglob("*.gz"))), 1)
        stored = json.loads((self.tmp / "two" / "world.json").read_text(encoding="utf-8"))
        self.assertEqual(world.internalise_blobs(stored)["tiles"], shared)

    def test_an_unreadable_save_stops_collection_entirely(self):
        """A save whose references cannot be counted must not license deletion."""
        self.write_slot("good", world.externalise_blobs({"tiles": self.big("a")}))
        broken = self.tmp / "broken"
        broken.mkdir()
        (broken / "world.json").write_text("{ this is not json", encoding="utf-8")
        report = world.gc_campaign_blobs()
        self.assertIn("skipped", report)
        self.assertEqual(report["removed"], 0)
        self.assertTrue(list(world.campaign_blobs_dir().rglob("*.gz")))

    def test_collection_is_safe_with_no_store_yet(self):
        self.assertEqual(world.gc_campaign_blobs()["removed"], 0)


if __name__ == "__main__":
    unittest.main()
