"""Item fixes from the seventh Saltmarrow run on Qwen2.5 7B (MLE), the player played by an agent."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-7b-run7-"))
_ENV = isolated_data_env(str(_TMP))
_SAVED_ENV: dict[str, str | None] = {}


def setUpModule():
    _SAVED_ENV.update({key: os.environ.get(key) for key in _ENV})
    os.environ.update(_ENV)


def tearDownModule():
    for key, value in _SAVED_ENV.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


T6_LINE = (
    "I pick the nearest half-buried house and dig at the mud around its doorway with my hands, "
    "looking for anything metal worth hauling back before the water returns."
)
T6_PROSE = (
    "You dig at the mud around the doorway of the nearest half-buried house, searching for anything metal that "
    "might be worth hauling away before the water returns. The mud is hard-packed, and your hands soon find a "
    "rusty tool handle. You pull it free and wipe the grime off, a piece of salvage you can use or sell. Nearby, "
    "a gravedigger named Bertram Lacey watches you, curious but not interfering.\n\n"
    "You return the tool to your inventory and continue your search. The water level seems to be rising, and you "
    "must hurry if you want to find more before it's too late."
)
T7_LINE = (
    "I keep the rusty tool handle I pulled out of the mud and call over to the gravedigger. "
    "\"Bertram, isn't it? Not much call for graves out here. What are you digging for?\""
)
T7_PROSE = (
    "You keep the rusty tool handle you pulled out of the mud and call over to the gravedigger, Bertram. "
    "\"Bertram, isn't it? Not much call for graves out here. What are you digging for?\"\n\n"
    "Bertram squints into the murky water. \"There's a chest down there. I've been trying to figure out how to "
    "lift it without too much disturbance.\"\n\n"
    "Bertram nods and starts to gather some wooden poles and rope from nearby. Together, you manage to pull the "
    "chest up from the well.\n\n"
    "Bertram agrees, and you both walk the chest and coins to the nearest official at the harbour, where you hand "
    "them over."
)


def _conn():
    from app.db import connect, init_db

    init_db()
    conn = connect()
    conn.execute("DELETE FROM inventory")
    conn.execute("DELETE FROM journal")
    return conn


class SearchingToHaulAsksForTheFind(unittest.TestCase):
    """T6: the dig's find was refused as taken without asking, and its sentences trimmed."""

    def test_intent(self):
        from app.llm import player_take_intent

        self.assertTrue(player_take_intent(T6_LINE))
        self.assertTrue(player_take_intent("I root around in the wreck for anything I can sell."))
        self.assertTrue(player_take_intent("I dig through the silt for something to haul home."))
        self.assertFalse(player_take_intent("I search the room for clues."))
        self.assertFalse(player_take_intent("Is the wreck worth the trip?"))
        # Not a purchase (T2): "a crew I can't pay for".
        self.assertFalse(player_take_intent("\"A sunken cargo needs a crew I can't pay for, Oriel.\" I tap the board."))
        self.assertTrue(player_take_intent("I'll pay 2 gold for it."))

    def test_the_find_is_kept(self):
        from app import world

        with _conn() as conn:
            rejected: list = []
            kept = world._filter_inventory_changes(
                conn,
                [{"name": "rusty tool handle", "quantity_delta": 1}],
                narration=T6_PROSE,
                player_input=T6_LINE,
                draft_narration=T6_PROSE,
                rejected=rejected,
            )
        self.assertEqual([c["name"] for c in kept], ["rusty tool handle"])
        self.assertEqual(rejected, [])


class KeepingLastTurnsFind(unittest.TestCase):
    """T7: 'I keep the rusty tool handle I pulled out of the mud' granted nothing."""

    def test_a_pronoun_scenes_later_is_not_the_thing(self):
        from app import world

        with _conn() as conn:
            added = world._grant_shown_takes(conn, [], T7_PROSE, T7_LINE)
        self.assertEqual([a["name"] for a in added], ["rusty tool handle"])

    def test_a_put_back_right_after_still_counts(self):
        from app import world

        with _conn() as conn:
            added = world._grant_shown_takes(
                conn, [], "You take the rusty key and put it back on the shelf.", "I take the rusty key."
            )
        self.assertEqual(added, [])

    def test_named_by_the_refusal_when_no_scene_names_it(self):
        from app import world

        with _conn() as conn:
            conn.execute("UPDATE pacing SET value = '7' WHERE key = 'turn'")
            conn.execute(
                "INSERT INTO journal (turn, kind, content) VALUES (7, 'inventory_reject', ?)",
                ("Rejected unearned gain: rusty tool handle x1 (named=True, prose_says_arrived=False, "
                 "prose_outcome=gain, owned=False, taken_without_player_asking=True)",),
            )
            conn.execute(
                "INSERT INTO journal (turn, kind, content) VALUES (7, 'narration', ?)",
                ("You pull it free and wipe the grime off.",),
            )
            added = world._grant_shown_takes(
                conn, [], "You keep it and call over to the gravedigger, who looks up from the well.",
                "I keep the handle I pulled out of the mud.",
            )
        self.assertEqual([a["name"] for a in added], ["rusty tool handle"])


class AJobIsNotAThing(unittest.TestCase):
    """T2: GRANT "deck work" "small" put 'deck work x1' in the pack."""

    PROSE = (
        "Oriel Rendle glances up from her sorting. \"There's a small job of cleaning the decks. You can start "
        "there and see what else you can salvage. As for pay, it's a meager share, half the usual.\""
    )
    LINE = "\"A sunken cargo needs a crew I can't pay for, Oriel.\" I tap the board. \"Anything I can do alone?\""

    def test_refused(self):
        from app import world

        with _conn() as conn:
            rejected: list = []
            kept = world._filter_inventory_changes(
                conn, [{"name": "deck work", "quantity_delta": 1}], narration=self.PROSE, player_input=self.LINE,
                draft_narration=self.PROSE, rejected=rejected,
            )
        self.assertEqual(kept, [])
        self.assertEqual([r["name"] for r in rejected], ["deck work"])

    def test_a_handed_over_thing_with_such_a_name_stands(self):
        from app import world

        prose = "Oriel hands you a work order, stamped with the guild's mark."
        with _conn() as conn:
            kept = world._filter_inventory_changes(
                conn, [{"name": "work order", "quantity_delta": 1}], narration=prose,
                player_input="I ask for the paperwork.", draft_narration=prose, rejected=[],
            )
        self.assertEqual([c["name"] for c in kept], ["work order"])

    def test_abstract_heads(self):
        from app import world

        self.assertTrue(world._abstract_grant(["deck", "work"]))
        self.assertTrue(world._abstract_grant(["half", "pay"]))
        self.assertFalse(world._abstract_grant(["work", "glove"]))
        self.assertFalse(world._abstract_grant(["rusty", "tool", "handle"]))


class ARefusedFindLeavesNoDanglingBeat(unittest.TestCase):
    """T6: trimming the find left 'You pull it free' and 'You return the tool to your inventory'."""

    def test_follow_on_and_stash_go_with_it(self):
        from app import world

        result = {"narration": T6_PROSE, "inventory_changes": []}
        rejected = [{"name": "rusty tool handle", "tokens": ["rusty", "tool", "handle"], "outcome": "gain"}]
        with _conn() as conn:
            report = world._reconcile_prose_with_state(
                conn, result, rejected=rejected, movement_report={}, gold_note=None, purse_note=None
            )
        text = world._narration_text(result)
        self.assertNotIn("rusty tool handle", text)
        self.assertNotIn("pull it free", text)
        self.assertNotIn("return the tool", text)
        self.assertIn("Bertram Lacey watches you", text)
        self.assertIn("water level seems to be rising", text)
        trimmed = [t for t in report["trimmed"] if t["why"] == "gain_refused"]
        self.assertEqual(len(trimmed[0]["sentences"]), 3)


if __name__ == "__main__":
    unittest.main()
