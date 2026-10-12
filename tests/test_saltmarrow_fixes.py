"""Fixes from the Saltmarrow API-bridge run (docs/showcase/saltmarrow-100-turns.md).

Each case pins one finding from docs/PLAYTEST_ISSUES.md #100-#122 or a reopened issue.
"""
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-saltmarrow-"))
_ENV = isolated_data_env(str(_TMP))
os.environ.update(_ENV)

from app import progression, prose_state, world  # noqa: E402
from app.player_resources import rest_healing  # noqa: E402

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


class LevelsComeFromXp(unittest.TestCase):
    """#121: 293 XP and still level 1, because only the model could raise a level."""

    def test_curve(self):
        self.assertEqual(progression.level_for_xp(0), 1)
        self.assertEqual(progression.level_for_xp(99), 1)
        self.assertEqual(progression.level_for_xp(100), 2)
        self.assertEqual(progression.level_for_xp(293), 2)
        self.assertEqual(progression.level_for_xp(300), 3)
        self.assertEqual(progression.level_progress(293, 2), {"level": 2, "xp": 293, "into_level": 193, "needed": 200, "next_level_at": 300})

    def test_sync_raises_and_journals_never_lowers(self):
        from app.db import connect, init_db

        init_db()
        with connect() as conn:
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.execute("DELETE FROM player")
            conn.execute(
                "INSERT INTO player (id, name, health, max_health, level, xp, gold, karma, current_location_id) "
                "VALUES (1, 'Isk', 20, 20, 1, 320, 0, 0, 0)"
            )
            self.assertEqual(progression.sync_level(conn, 5, enabled=True), 3)
            self.assertEqual(conn.execute("SELECT level FROM player").fetchone()[0], 3)
            notes = [r[0] for r in conn.execute("SELECT content FROM journal WHERE kind = 'level_up'")]
            self.assertEqual(len(notes), 2)
            conn.execute("UPDATE player SET level = 7")
            self.assertIsNone(progression.sync_level(conn, 6, enabled=True))
            self.assertEqual(conn.execute("SELECT level FROM player").fetchone()[0], 7)
            conn.execute("UPDATE player SET level = 1, xp = 900")
            self.assertIsNone(progression.sync_level(conn, 7, enabled=False))


class SleepHeals(unittest.TestCase):
    """#120: 13 and 17 hours of sleep healed nothing."""

    def test_amounts(self):
        self.assertEqual(rest_healing(minutes=817, kind="sleep", health=9, max_health=20), 6)
        self.assertEqual(rest_healing(minutes=120, kind="sleep", health=9, max_health=20), 1)
        self.assertEqual(rest_healing(minutes=480, kind="meditate", health=9, max_health=20), 2)
        self.assertEqual(rest_healing(minutes=600, kind="wait", health=9, max_health=20), 0)
        self.assertEqual(rest_healing(minutes=900, kind="sleep", health=19, max_health=20), 1)


class NamedCoinIsExact(unittest.TestCase):
    """#69/#96 reopened: spelled sums the op and prose agree on were re-rolled."""

    def _settle(self, gold, narration, line):
        result = {"narration": narration, "player": {"gold_delta": gold}}
        note = world._settle_stated_gold(result, line)
        return result["player"].get("gold_delta"), note

    def test_mentions(self):
        self.assertEqual(prose_state.coin_mentions("Nine coins. All you had."), [9])
        self.assertEqual(prose_state.coin_mentions("three coins, then 2 gold"), [3, 2])

    def test_loss_named_without_paying_verb(self):
        value, note = self._settle(-9, "He takes the purse. Nine coins. All you had.", "Take my purse.")
        self.assertEqual(value, -9)
        self.assertEqual(note["source"], "stated_mention")

    def test_modest_gain_named(self):
        value, _ = self._settle(9, "Tam holds out your own purse. It clinks. Nine coins.", "I wait.")
        self.assertEqual(value, 9)

    def test_large_or_unnamed_gain_still_rolls(self):
        self.assertIsNone(self._settle(250, "The reeve gives you 250 gold.", "I wait.")[1])
        self.assertIsNone(self._settle(9, "Tam gives you your purse back.", "I wait.")[1])

    def test_put_down_is_an_offer(self):
        self.assertEqual(prose_state.player_trade_offer("I put three coin on the counter for the rope."), 3)
        self.assertEqual(prose_state.stated_coin_amounts("You count three coins out of your purse.")["paid"], [3])


class NameRepairLeavesSentencesAlone(unittest.TestCase):
    """#107: "Tam Kemp [[H]] Turn and wedge" and "H. says" became another name."""

    NAMES = {"H": "Hereward", "T": "Tam Kemp"}

    def _repair(self, text):
        from app import llm

        return llm._repair_prose_entity_labels(text, self.NAMES)

    def test_capital_order_untouched(self):
        out = self._repair("Hereward [[H]] points at the cleat. Turn and wedge.")
        self.assertIn(". Turn and wedge.", out)
        self.assertNotIn("Tam Kemp Turn", out)

    def test_quoted_line_untouched(self):
        out = self._repair('Hereward [[H]] shrugs. "Ask her. says the harbour."')
        self.assertIn('"Ask her. says the harbour."', out)

    def test_initial_untouched(self):
        out = self._repair("The ledger is signed H. says nothing more.")
        self.assertNotIn("Tam Kemp says", out)
        self.assertNotIn("Hereward says", out)

    def test_real_hole_still_filled(self):
        out = self._repair("The rope goes slack. — leans against the rail.")
        self.assertRegex(out, r"(Hereward|Tam Kemp) leans against")


class TravelSceneIsNotCut(unittest.TestCase):
    """#111: a rowing trip was cut back to "You take the stern"."""

    LINE = "Mam and I go down the harbour stairs to Hereward's skiff, and he rows us out to the customs tower."

    def test_take_a_position_is_not_taking(self):
        from app import llm

        self.assertEqual(llm._invented_unit_family("You take the stern.", self.LINE, self.LINE), "")
        self.assertEqual(llm._invented_unit_family("You take the bread.", "I ask about bread", "I ask about bread"), "taking")

    def test_travel_line_keeps_the_scene(self):
        from app import llm

        narration = (
            "Hereward [[H]] unties the skiff. You take the stern. " * 6
            + "The tower rises out of the grey. A clerk asks for your name and you give it."
        )
        out = llm._cut_scene_at_invented_request({"narration": narration, "self_check": {}}, self.LINE)
        self.assertFalse(out.get("_scene_cut"))
        self.assertEqual(out["narration"], narration)


class ChecksReadThePlayersLine(unittest.TestCase):
    """#89 reopened, #102: the engine's own note rolled persuasion every turn; keywords misread acts."""

    NOTE = (
        "\n\nResolved player references: Conversation (engine decided) - the player is talking to "
        "Tam Kemp [[H]]. Only Tam Kemp [[H]] answers the player."
    )

    def _skill(self, line, context=None):
        from app.skill_checks import infer_check_from_action

        check = infer_check_from_action(line, context or {})
        return check and check["skill_code"]

    def test_engine_note_rolls_nothing(self):
        line = "Tam and I set the iron bar against the bollard and walk the line round it a turn at a time."
        self.assertIsNone(self._skill(line + self.NOTE))
        self.assertIsNone(self._skill("I step back out onto the wall and head out along the deep channel." + self.NOTE))

    def test_keyword_misreads(self):
        self.assertIsNone(self._skill("I lie flat and crawl up the ramp on my belly."))
        self.assertIsNone(self._skill("I tie the rope round Tam's waist, then round mine."))
        self.assertIsNone(self._skill("\"No cart's worth you.\""))
        self.assertIsNone(self._skill("I stay by the board and wait. I'm not hiding."))
        self.assertIsNone(self._skill("I strike the flint over the wick until it catches."))
        self.assertIsNone(self._skill("I climb into the skiff beside Hereward."))
        self.assertIsNone(self._skill("I keep hold of the rope and watch how fast the water climbs the tiles."))

    def test_real_acts_still_roll(self):
        self.assertEqual(self._skill("I strike him with my staff"), "melee")
        self.assertEqual(self._skill("he strikes at the guard"), "melee")
        self.assertEqual(self._skill("I lie to the reeve about the cart"), "deception")
        self.assertEqual(self._skill("what is the ring worth?"), "appraise")
        self.assertEqual(self._skill("I mine for iron"), "mining")
        self.assertEqual(self._skill("I climb the sea wall"), "athletics")
        self.assertEqual(self._skill("I don't wait and hide behind the crates"), "stealth")

    def test_opponent_is_the_addressee_not_a_listener(self):
        from app.skill_checks import infer_check_from_action

        people = [{"code": "K", "name": "Mara Tarrow"}, {"code": "H", "name": "Tam Kemp"}]
        ctx = {"npcs": people, "conversation_turn": {"addressed": ["H"]}}
        check = infer_check_from_action("I ask him which channel he took.", ctx)
        self.assertEqual(check["opposition"]["name"], "Tam Kemp")
        named = infer_check_from_action("I ask Mara which channel Tam took.", ctx)
        self.assertEqual(named["opposition"]["name"], "Mara Tarrow")
        nobody = infer_check_from_action("I ask which channel he took.", {"npcs": people})
        self.assertIsNone(nobody["opposition"])


if __name__ == "__main__":
    unittest.main()
