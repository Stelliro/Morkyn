"""7B run 6 money fixes: one coin event pays once, coin put away is not new, a coin GRANT keeps its sentence."""
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-7b-run6-money-"))
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


# Run 6, T9 (the scene that paid) and T10 (the line after it), as shipped.
T9_PROSE = (
    "Oldfield [[B]] gives you a nod of approval. \"Well, you've earned this.\" "
    "He hands you a small pouch containing two gold coins."
)
T10_LINE = 'I pocket the two gold and look around for Isolde. "Isolde, is it? Who\'s the tallow chandler in town these days?"'
T10_PROSE = (
    "You pocket the two gold and look around for Isolde [[C]]. \"Isolde, is it? Who's the tallow chandler "
    "in town these days?\" Oldfield [[B]] gives you a curious look but says nothing."
)


def _turn(narration, player=None, changes=None):
    return {"narration": narration, "player": dict(player or {}), "inventory_changes": list(changes or [])}


class Readers(unittest.TestCase):
    def test_line_puts_coin_away(self):
        from app.prose_state import player_puts_away_coin as away

        self.assertEqual(away(T10_LINE), 2)
        self.assertEqual(away("I pocket the coins and thank him."), 0)
        self.assertIsNone(away("I pocket two gold from the till."))
        self.assertIsNone(away("I pocket the gold from the table."))
        self.assertIsNone(away('"I pocket the two gold," I joke.'))
        self.assertIsNone(away("I keep the fitting."))

    def test_coin_reached_player(self):
        from app.prose_state import coin_reached_player as reached

        self.assertTrue(reached(T9_PROSE, 2))
        self.assertFalse(reached(T9_PROSE, 5))
        self.assertFalse(reached("The rain keeps falling on the yard.", 2))

    def test_coin_grant_with_a_stray_argument_is_coin(self):
        from app import world

        self.assertTrue(world._coin_name_match("two gold coins, none"))
        self.assertTrue(world._is_coin_item({"name": "two gold coins, none", "quantity_delta": 1}))
        self.assertFalse(world._coin_name_match("brass fitting, worn"))


class Settle(unittest.TestCase):
    def setUp(self):
        from app.db import init_db

        init_db()

    def _settle(self, result, line, narrations=()):
        from app import world
        from app.db import connect

        with connect() as conn:
            conn.execute("DELETE FROM journal")
            for text in narrations:
                conn.execute("INSERT INTO journal (turn, kind, content) VALUES (1, 'narration', ?)", (text,))
            return world._settle_stated_gold(result, line, conn=conn)

    def test_t9_coin_grant_settles_once_and_leaves_the_pack(self):
        result = _turn(T9_PROSE, changes=[{"name": "two gold coins, none", "quantity_delta": 1}])
        note = self._settle(result, "Oldfield. Two gold, by noon, we said.")
        self.assertEqual(result["player"]["gold_delta"], 2, note)
        self.assertEqual(result["inventory_changes"], [])

    def test_t10_coin_put_away_after_it_arrived_is_not_new(self):
        result = _turn(T10_PROSE)
        self._settle(result, T10_LINE, narrations=[T9_PROSE])
        self.assertNotIn("gold_delta", result["player"])
        self.assertNotIn("gold_band", result["player"])
        self.assertTrue(result.get("_coin_restated"))

    def test_t10_model_gold_op_for_the_same_coin_is_dropped(self):
        result = _turn(T10_PROSE, player={"gold_delta": 2})
        self._settle(result, T10_LINE, narrations=[T9_PROSE])
        self.assertNotIn("gold_delta", result["player"])

    def test_pocketing_with_no_earlier_payment_still_counts(self):
        # Nothing handed coin over before: the usual reading stands.
        result = _turn("Warin hands you 6 gold and you pocket the coins.")
        self._settle(result, "I pocket the coins.", narrations=["The rain keeps falling on the yard."])
        self.assertEqual(result["player"]["gold_delta"], 6)
        self.assertFalse(result.get("_coin_restated"))


class CoinsToGold(unittest.TestCase):
    def setUp(self):
        from app.db import init_db

        init_db()

    def test_coin_item_pays_once_when_gold_already_moves(self):
        from app import world
        from app.db import connect

        with connect() as conn:
            before = int(conn.execute("SELECT gold FROM player WHERE id = 1").fetchone()[0] or 0) if conn.execute(
                "SELECT 1 FROM player WHERE id = 1").fetchone() else None
            if before is None:
                conn.execute("INSERT INTO player (id, name, gold) VALUES (1, 'Isk', 14)")
                before = 14
            kept = world._coins_to_gold(conn, [{"name": "two gold", "quantity_delta": 1}], T10_PROSE, gold_moving=True)
            after = int(conn.execute("SELECT gold FROM player WHERE id = 1").fetchone()[0])
        self.assertEqual(kept, [])
        self.assertEqual(after, before)


class ThroughTheTurn(unittest.TestCase):
    """apply_turn with run 6's T9 and T10: +2 once, and the paying sentence stays."""

    def setUp(self):
        from app import db, rng, world

        db.init_db()
        rng.reset_seed_cache()
        world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})

    def _gold(self):
        from app import db

        with db.connect() as conn:
            return int(conn.execute("SELECT gold FROM player WHERE id = 1").fetchone()[0])

    def _apply(self, prose, line, changes=()):
        from app import world

        turn = _turn(prose, changes=changes)
        turn["self_check"] = {"passed": True, "issues_found": [], "corrections_made": []}
        turn["turn_summary"] = "test"
        world.apply_turn(turn, line)
        return turn

    def test_t9_then_t10(self):
        start = self._gold()
        t9 = self._apply(T9_PROSE, "Oldfield. Two gold, by noon, we said. It's not noon and the pile's done.",
                         changes=[{"name": "two gold coins, none", "quantity_delta": 1}])
        self.assertEqual(self._gold(), start + 2)
        from app import world

        self.assertIn("He hands you a small pouch containing two gold coins.", world._narration_text(t9))
        self._apply(T10_PROSE, T10_LINE, changes=[{"name": "two gold", "quantity_delta": 1}])
        self.assertEqual(self._gold(), start + 2)
        from app import db

        with db.connect() as conn:
            names = [r[0] for r in conn.execute("SELECT name FROM inventory WHERE quantity > 0")]
        self.assertFalse([n for n in names if "gold" in n.lower()], names)


if __name__ == "__main__":
    unittest.main()
