"""Regression tests: a character keeps the pronouns they were introduced with.

From the 100-turn continuity probe. Counting only sentences that named exactly
one NPC, the bargeman Jetcoil was "he/his" 41 times and "they/their" 128 times
in the same run. No gender flip -- nothing ever said which was right, so the
model re-decided every turn.

Fix is the same shape as the venue keeper: infer once from the prose that first
commits, pin it on the row, and state it in the packet from then on. Inference
is never repeated, because re-inferring is the drift.

Run:  python -m unittest tests.test_npc_pronouns
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-pronoun-test-"))
_ENV = {
    "AI_RPG_DB": str(_TMP / "world.db"),
    "AI_RPG_PACK_DIR": str(_TMP / "packs"),
    "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
    "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
    "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
    "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
}
os.environ.update(_ENV)

from app.db import connect, db_path, init_db  # noqa: E402
from app.world import (  # noqa: E402
    bind_npc_pronouns,
    cast_pronoun_contract,
    infer_npc_pronouns,
    narrative_voice_contract,
    pronoun_set_for,
)


def _assert_isolated() -> None:
    if not str(db_path()).startswith(str(_TMP)):
        raise AssertionError(f"test isolation failed: AI_RPG_DB resolves to {db_path()!r}")


def setUpModule() -> None:
    """Re-pin paths: unittest imports every test module before running any test."""
    os.environ.update(_ENV)
    _assert_isolated()


_assert_isolated()
init_db()


class TestInference(unittest.TestCase):
    def test_masculine_prose_reads_as_he(self):
        text = "Jetcoil leans on the post, his hands raw. He watches the water."
        self.assertEqual(infer_npc_pronouns("Jetcoil", text), "he")

    def test_feminine_prose_reads_as_she(self):
        text = "Mara counts the coins. She frowns at her ledger."
        self.assertEqual(infer_npc_pronouns("Mara", text), "she")

    def test_mixed_or_absent_signal_stays_unset(self):
        # Better to leave it unpinned than to pin a guess: an unset NPC defaults
        # to they/them, a wrongly pinned one is stated as truth every turn.
        self.assertEqual(infer_npc_pronouns("Jetcoil", "Jetcoil nods at the crowd."), "")
        self.assertEqual(infer_npc_pronouns("Jetcoil", "He and she argue near Jetcoil."), "")
        self.assertEqual(infer_npc_pronouns("", "He walks."), "")
        self.assertEqual(infer_npc_pronouns("Jetcoil", ""), "")

    def test_only_sentences_naming_this_npc_count(self):
        # Mara's sentence must not gender Jetcoil.
        text = "Mara counts her coins. Jetcoil watches the barge."
        self.assertEqual(infer_npc_pronouns("Jetcoil", text), "")


class TestPinningIsWriteOnce(unittest.TestCase):
    def _npc(self, name: str, pronouns: str = ""):
        with connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO locations (id, code, name) VALUES (1, 'L1', 'Gate')"
            )
            conn.execute(
                "INSERT INTO npcs (code, location_id, name, pronouns) VALUES (?, 1, ?, ?)",
                (name[:3].upper(), name, pronouns),
            )
            row = conn.execute("SELECT id, name, pronouns FROM npcs WHERE name = ?", (name,)).fetchone()
            return dict(row)

    def test_first_commitment_is_pinned(self):
        npc = self._npc("Dockrest")
        with connect() as conn:
            bound = bind_npc_pronouns(conn, "Dockrest mends his net. He does not look up.", [npc])
            self.assertEqual(len(bound), 1)
            row = conn.execute("SELECT pronouns FROM npcs WHERE id = ?", (npc["id"],)).fetchone()
        self.assertEqual(str(row["pronouns"]), "he")

    def test_an_already_pinned_npc_is_never_re_inferred(self):
        npc = self._npc("Saltwick", pronouns="she")
        with connect() as conn:
            bound = bind_npc_pronouns(conn, "Saltwick lifts his crate. He grunts.", [npc])
            row = conn.execute("SELECT pronouns FROM npcs WHERE id = ?", (npc["id"],)).fetchone()
        self.assertEqual(bound, [], "a pinned NPC must not be revisited")
        self.assertEqual(str(row["pronouns"]), "she")

    def test_prose_with_no_signal_leaves_the_npc_unpinned(self):
        npc = self._npc("Cinderpath")
        with connect() as conn:
            bound = bind_npc_pronouns(conn, "Cinderpath waits by the fire.", [npc])
            row = conn.execute("SELECT pronouns FROM npcs WHERE id = ?", (npc["id"],)).fetchone()
        self.assertEqual(bound, [])
        self.assertEqual(str(row["pronouns"]), "")


class TestContract(unittest.TestCase):
    def test_unset_npcs_default_to_they(self):
        state = {
            "current_location": {"id": 1},
            "locations": [{"id": 1, "npcs": [{"name": "Hearthrow", "code": "I", "pronouns": ""}]}],
        }
        cast = cast_pronoun_contract(state)
        self.assertEqual(cast[0]["subject"], "they")
        self.assertEqual(cast[0]["possessive"], "their")

    def test_pinned_npcs_are_stated(self):
        state = {
            "current_location": {"id": 1},
            "locations": [{"id": 1, "npcs": [{"name": "Jetcoil", "code": "D", "pronouns": "he"}]}],
        }
        cast = cast_pronoun_contract(state)
        self.assertEqual(cast[0]["name"], "Jetcoil")
        self.assertEqual(cast[0]["subject"], "he")

    def test_only_the_current_location_is_listed(self):
        state = {
            "current_location": {"id": 1},
            "locations": [
                {"id": 1, "npcs": [{"name": "Here", "code": "A", "pronouns": "she"}]},
                {"id": 2, "npcs": [{"name": "Elsewhere", "code": "B", "pronouns": "he"}]},
            ],
        }
        names = [c["name"] for c in cast_pronoun_contract(state)]
        self.assertEqual(names, ["Here"])

    def test_voice_contract_carries_the_cast_and_a_rule(self):
        state = {
            "player": {"name": "Ash", "sex": ""},
            "settings": {},
            "current_location": {"id": 1},
            "locations": [{"id": 1, "npcs": [{"name": "Jetcoil", "code": "D", "pronouns": "he"}]}],
        }
        contract = narrative_voice_contract(state)
        self.assertTrue(contract["cast_pronouns"])
        self.assertIn("same character", contract["cast_rule"])

    def test_no_cast_means_no_rule_text(self):
        state = {"player": {"name": "Ash", "sex": ""}, "settings": {}, "locations": []}
        self.assertEqual(narrative_voice_contract(state)["cast_rule"], "")

    def test_pronoun_sets_are_complete(self):
        for key in ("he", "she", "they"):
            with self.subTest(key=key):
                s = pronoun_set_for(key)
                self.assertEqual(set(s), {"subject", "object", "possessive"})
        self.assertEqual(pronoun_set_for("nonsense")["subject"], "they")


if __name__ == "__main__":
    unittest.main()
