"""
Per-turn autosave history, kept per character.

Ten turns per character, five once a character has been idle for months. The
old behaviour was a single "last" slot overwritten every turn, so the only
recoverable point was the turn you just played -- and starting a new game wipes
the live database outright with no copy taken.

Archived saves stay listed and stay loadable. Archiving is about reclaiming
room from a character you have finished with, not hiding them.
"""

import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from app import world

CID = "3f9a1c2b"
OTHER = "0011aabb"


class AutosaveHistoryTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="morkyn-auto-"))
        patcher = mock.patch.dict(os.environ, {"AI_RPG_CAMPAIGN_SLOTS": str(self.tmp)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def make_save(self, name, saved_at=None, payload=None):
        slot = self.tmp / name
        slot.mkdir(parents=True, exist_ok=True)
        (slot / "world.json").write_text(json.dumps(payload or {"tables": {}}), encoding="utf-8")
        meta = {"slot": name, "saved_at": (saved_at or datetime.now(timezone.utc)).isoformat()}
        (slot / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
        return slot

    def make_turns(self, cid, turns, saved_at=None):
        for turn in turns:
            self.make_save(world.autosave_slot_name(cid, turn), saved_at=saved_at)


class SlotNamingTests(unittest.TestCase):
    def test_names_sort_in_turn_order_as_text(self):
        names = [world.autosave_slot_name(CID, t) for t in (2, 10, 9, 100)]
        self.assertEqual(sorted(names), [world.autosave_slot_name(CID, t) for t in (2, 9, 10, 100)])

    def test_a_name_round_trips(self):
        self.assertEqual(world.parse_autosave_slot(world.autosave_slot_name(CID, 7)), (CID, 7))

    def test_ordinary_save_names_are_not_autosaves(self):
        for name in ("last", "Kael_Veyra", "pre_grok_session", "auto", "auto-xyz-t1"):
            self.assertIsNone(world.parse_autosave_slot(name), name)


class ListingTests(AutosaveHistoryTestCase):
    def test_lists_newest_turn_first(self):
        self.make_turns(CID, [1, 5, 3])
        self.assertEqual([s["auto_turn"] for s in world.list_autosaves(CID)], [5, 3, 1])

    def test_other_characters_are_not_included(self):
        self.make_turns(CID, [1, 2])
        self.make_turns(OTHER, [1])
        self.assertEqual(len(world.list_autosaves(CID)), 2)
        self.assertEqual(len(world.list_autosaves()), 3)

    def test_named_saves_are_never_listed_as_autosaves(self):
        self.make_save("Kael_Veyra")
        self.make_save("last")
        self.assertEqual(world.list_autosaves(), [])


class PruningTests(AutosaveHistoryTestCase):
    def test_a_character_is_held_to_ten_turns(self):
        self.make_turns(CID, range(1, 16))
        report = world.prune_autosaves(CID)
        self.assertEqual(report["kept"], world.AUTOSAVE_HISTORY_KEEP)
        kept = [s["auto_turn"] for s in world.list_autosaves(CID)]
        self.assertEqual(kept, list(range(15, 5, -1)), "the ten most recent turns survive")

    def test_pruning_one_character_leaves_another_alone(self):
        self.make_turns(CID, range(1, 15))
        self.make_turns(OTHER, range(1, 4))
        world.prune_autosaves(CID)
        self.assertEqual(len(world.list_autosaves(OTHER)), 3)

    def test_named_saves_are_never_pruned(self):
        self.make_save("Kael_Veyra")
        self.make_turns(CID, range(1, 20))
        world.prune_autosaves(CID)
        self.assertTrue((self.tmp / "Kael_Veyra").exists())

    def test_pruning_under_the_limit_removes_nothing(self):
        self.make_turns(CID, [1, 2, 3])
        self.assertEqual(world.prune_autosaves(CID)["removed"], [])


class ArchiveTests(AutosaveHistoryTestCase):
    def test_an_idle_character_is_thinned_to_five(self):
        old = datetime.now(timezone.utc) - timedelta(days=120)
        self.make_turns(CID, range(1, 11), saved_at=old)
        world.archive_idle_campaigns()
        kept = [s["auto_turn"] for s in world.list_autosaves(CID)]
        self.assertEqual(kept, [10, 9, 8, 7, 6], "the five most recent turns survive")

    def test_an_active_character_is_untouched(self):
        self.make_turns(CID, range(1, 11), saved_at=datetime.now(timezone.utc))
        world.archive_idle_campaigns()
        self.assertEqual(len(world.list_autosaves(CID)), 10)

    def test_recency_is_judged_on_the_newest_save_not_the_oldest(self):
        """A long-running character has old turns; that is not the same as idle."""
        self.make_turns(CID, [1, 2], saved_at=datetime.now(timezone.utc) - timedelta(days=200))
        self.make_turns(CID, [3], saved_at=datetime.now(timezone.utc))
        world.archive_idle_campaigns()
        self.assertEqual(len(world.list_autosaves(CID)), 3)

    def test_survivors_are_marked_so_the_ui_can_say_so(self):
        old = datetime.now(timezone.utc) - timedelta(days=120)
        self.make_turns(CID, range(1, 11), saved_at=old)
        world.archive_idle_campaigns()
        for save in world.list_autosaves(CID):
            self.assertTrue(save.get("archived"), f"{save['slot']} should be marked archived")

    def test_archived_saves_stay_visible_and_loadable(self):
        old = datetime.now(timezone.utc) - timedelta(days=120)
        self.make_turns(CID, range(1, 11), saved_at=old)
        world.archive_idle_campaigns()
        listed = {s["slot"] for s in world.list_campaign_slots()}
        for save in world.list_autosaves(CID):
            self.assertIn(save["slot"], listed)
            self.assertTrue((self.tmp / save["slot"] / "world.json").exists())

    def test_one_idle_character_does_not_thin_an_active_one(self):
        self.make_turns(CID, range(1, 11), saved_at=datetime.now(timezone.utc) - timedelta(days=200))
        self.make_turns(OTHER, range(1, 11), saved_at=datetime.now(timezone.utc))
        world.archive_idle_campaigns()
        self.assertEqual(len(world.list_autosaves(CID)), 5)
        self.assertEqual(len(world.list_autosaves(OTHER)), 10)


if __name__ == "__main__":
    unittest.main()
