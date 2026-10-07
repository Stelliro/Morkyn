"""
Review of the player-agency pass and the depth-retry name check under the
writer-off default (AI_RPG_NARRATION_PIPELINE=0).

The draft's own prose ships now, so the pass that drops what the narration did
for the player runs on every turn. These cases are where it removed what the
player asked for, disagreed with the grant gate, shipped a fragment, or where
the depth retry was thrown away over a pronoun. Live text is verbatim from
tests/fixtures/playtest_batch6_agency_review.json.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn_b6_agency_"))
os.environ.update(isolated_data_env(str(_TMP)))
for _key, _name in (
    ("AI_RPG_IDEA_BANK", "idea_bank.json"),
    ("AI_RPG_LAUNCHER_PREFS", "launcher_prefs.json"),
    ("AI_RPG_SKILL_LIBRARY", "skill_library.json"),
):
    os.environ.setdefault(_key, str(_TMP / _name))
os.environ.setdefault("AI_RPG_PACK_DIR", str(_TMP / "packs"))

from app import llm, world  # noqa: E402

WRITER_OFF = {
    "AI_RPG_NARRATION_PIPELINE": "0",
    "AI_RPG_NARRATION_PIPELINE_CONSOLIDATE": "1",
    "AI_RPG_FAST_VERIFICATION": "1",
    "AI_RPG_DSL_SKIP_VERIFY": "1",
    "AI_RPG_DRAFT_MODE": "dsl",
}
FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "playtest_batch6_agency_review.json").read_text(encoding="utf-8"))

# Distinct filler so the turn-level pass clears its 200-character floor.
FILL = (
    "The lane bends west under a low grey sky, and the hedgerows on either side stand tall and dense. "
    "Somewhere beyond them a wood pigeon calls, the same three notes over and over. "
    "A cart rut full of rainwater catches the light, and the air smells of wet earth and crushed nettle."
)


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE inventory (id INTEGER PRIMARY KEY, name TEXT, quantity INTEGER, dimensional_space INTEGER DEFAULT 0)")
    conn.execute("CREATE TABLE journal (id INTEGER PRIMARY KEY, turn INTEGER, kind TEXT, content TEXT)")
    return conn


def _overreach(narration: str, player_input: str) -> dict:
    turn = {"narration": narration, "self_check": {"corrections_made": []}}
    return llm._drop_player_overreach(turn, player_input, "test", [])


class WriterOffEnv(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, WRITER_OFF)
        patcher.start()
        self.addCleanup(patcher.stop)


class PerceptionPayoffIsKept(WriterOffEnv):
    """Finding 1: the pass deleted the result of the act the player asked for."""

    def test_live_b_g1_t3_keeps_the_etching_and_drops_only_the_pickup(self):
        live = FIXTURE["ab_B_g1_t3"]
        kept, dropped = llm.drop_invented_player_acts_text(live["draft_narration"], live["input"])
        self.assertIn("notice the faint etching of a symbol on its shaft", kept)
        self.assertNotIn("You pick it up", kept)
        self.assertEqual(len(dropped), 1)
        self.assertIn("pick it up", dropped[0])
        self.assertNotIn("etching", dropped[0])

    def test_live_b_g1_t3_turn_ops_still_stand_on_the_prose(self):
        live = FIXTURE["ab_B_g1_t3"]
        out = _overreach(live["draft_narration"], live["input"])
        final = out["narration"]
        # The claim and the talk topic are about the symbol on the nail.
        self.assertEqual(live["response_drafts"][0]["claim"], "the symbol on the nail is unfamiliar")
        self.assertIn("symbol", final)
        self.assertIn("nail", final)
        self.assertIn("don’t recognize", final)
        # The pickup was the model's, not the player's: no grant for it.
        kept = world._filter_inventory_changes(
            _conn(), live["inventory_changes"], narration=final, player_input=live["input"],
            input_kind="action", draft_narration=live["draft_narration"],
        )
        self.assertEqual(kept, [])

    def test_listen_keeps_what_the_player_heard(self):
        text = "The voices beyond the door are low and urgent. You realize one of them is the innkeeper, and he sounds afraid."
        kept, dropped = llm.drop_invented_player_acts_text(text, "I listen at the door.")
        self.assertEqual(dropped, [])
        self.assertIn("he sounds afraid", kept)

    def test_read_and_search_keep_their_answers(self):
        for player, text in (
            ("I read the letter.", "The ink has run. You understand only a few words: a name, a date, and the word harbor."),
            ("I search the desk.", "The drawers stick. You remember the clerk mentioning a hidden latch."),
            ("I study the map.", "The coast is drawn with care. You know this bay; the reef is not marked."),
        ):
            kept, dropped = llm.drop_invented_player_acts_text(text, player)
            self.assertEqual(dropped, [], player)

    def test_a_non_perception_act_still_loses_invented_thought(self):
        text = "The guard waves the cart through. You realize the seal on the crate is forged."
        kept, dropped = llm.drop_invented_player_acts_text(text, "I walk to the gate.")
        self.assertEqual(len(dropped), 1)
        self.assertNotIn("forged", kept)

    def test_wondering_stays_the_players_own_even_after_looking(self):
        text = "The square is empty. You wonder if the cloaked figure was ever real."
        _, dropped = llm.drop_invented_player_acts_text(text, "I look around the square.")
        self.assertEqual(len(dropped), 1)

    def test_perception_half_after_a_dropped_gesture_or_take_stays(self):
        kept, dropped = llm.drop_invented_player_acts_text(
            "You pocket the coin and see a second one glinting under the bench.", "I look under the table."
        )
        self.assertEqual(kept, "You see a second one glinting under the bench.")
        self.assertEqual(dropped, ["You pocket the coin"])


class OneTakeVocabulary(WriterOffEnv):
    """Finding 2: the drop pass and the grant gate disagreed on what a take is."""

    CASES = (
        ("I forage for berries along the hedge.",
         "The hedge is heavy with fruit after the rain. You pocket a handful of ripe berries, their juice staining your fingers.",
         {"name": "ripe berries", "quantity_delta": 1, "source": "forage"}, "ripe berries"),
        ("I craft a torch from the rags.",
         "The rags are dry enough. You pick up the flint and strike until it catches, and the torch flares.",
         {"name": "torch", "quantity_delta": 1, "source": "craft"}, "flint"),
        ("I harvest some herbs from the bank.",
         "Wild thyme grows thick on the bank. You pocket a fistful of thyme sprigs.",
         {"name": "thyme sprigs", "quantity_delta": 1, "source": "found"}, "thyme sprigs"),
    )

    def test_take_words_keep_the_prose_and_the_grant_together(self):
        for player, scene, change, shown in self.CASES:
            narration = FILL + "\n\n" + scene
            out = _overreach(narration, player)
            final = out["narration"]
            self.assertIn(shown, final, player)
            self.assertFalse(out.get("_invented_player_acts"), player)
            kept = world._filter_inventory_changes(
                _conn(), [dict(change)], narration=final, player_input=player,
                input_kind="action", draft_narration=narration,
            )
            self.assertEqual([c["name"] for c in kept], [change["name"]], player)

    def test_without_a_take_word_both_refuse(self):
        player = "I walk along the hedge."
        narration = FILL + "\n\n" + "The hedge is heavy with fruit. You pocket a handful of ripe berries."
        out = _overreach(narration, player)
        self.assertNotIn("You pocket", out["narration"])
        kept = world._filter_inventory_changes(
            _conn(), [{"name": "ripe berries", "quantity_delta": 1, "source": "forage"}],
            narration=out["narration"], player_input=player, input_kind="action", draft_narration=narration,
        )
        self.assertEqual(kept, [])

    def test_the_two_passes_share_one_check(self):
        self.assertIs(world.player_take_intent, llm.player_take_intent)
        for line, want in (
            ("I forage for mushrooms", True), ("I receive the reward", True), ("I accept the gift", True),
            ("I keep the coin", True), ("I pick the satchel up", True), ("I take stock of my injuries", False),
            ("I take a look at the seed", False), ("I keep walking", False), ("I examine the ground", False),
            ("the first shop I can find", False),
        ):
            self.assertEqual(llm.player_take_intent(line), want, line)

if __name__ == "__main__":
    unittest.main()
