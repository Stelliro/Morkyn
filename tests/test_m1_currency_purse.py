"""m1 (Stell 2026-10-24/25, "go ahead" 2026-10-25): a currency set per world, the purse held as one number.

"i want to add copper, silver and gold as the currency, that way we can translate the currency into 1 form
... $69420 will be translated as 6 gold 94 silver and 20 copper, we should never rely on the llm to work out
the item cost by coin, just a single value". One unit is a copper in the coin set (1 silver = 100, 1 gold =
10,000); credits or bottle caps are their own sets. The purse is player.purse_units (app/purse.py); gold is
its whole-gold mirror. The model writes an amount as $<number> (base units) and the engine shows coins.

Run:  cd tests && ../.venv/bin/python -m unittest test_m1_currency_purse
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-m1-currency-"))
_ENV = isolated_data_env(str(_TMP))
_SAVED_ENV: dict[str, str | None] = {}


def setUpModule():
    _SAVED_ENV.update({key: os.environ.get(key) for key in _ENV})
    os.environ.update(_ENV)
    from app.db import init_db

    init_db()


def tearDownModule():
    for key, value in _SAVED_ENV.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _set_world(conn, options: dict | None, currency_set: str | None = None) -> None:
    conn.execute("DELETE FROM settings WHERE key IN ('currency_config', 'playthrough_options')")
    if options is not None:
        conn.execute("INSERT INTO settings (key, value) VALUES ('playthrough_options', ?)", (json.dumps(options),))
    if currency_set:
        from app import currency

        currency.update_currency_config(conn, {"set": currency_set})


class OldSaveMigratesOnce(unittest.TestCase):
    def test_gold_12_becomes_120000_units_once(self):
        from app import db
        from app.db import connect

        with connect().closing() as conn:
            _set_world(conn, {"world_style": "frontier dark fantasy"})
            conn.execute("DELETE FROM settings WHERE key = ?", (db.PURSE_MIGRATED_KEY,))
            conn.execute("UPDATE player SET gold = 12, purse_units = 0 WHERE id = 1")
            conn.commit()
        db.init_db()
        with connect().closing() as conn:
            row = conn.execute("SELECT gold, purse_units FROM player WHERE id = 1").fetchone()
            self.assertEqual((row["gold"], row["purse_units"]), (12, 120000))
            mark = json.loads(conn.execute("SELECT value FROM settings WHERE key = ?", (db.PURSE_MIGRATED_KEY,)).fetchone()[0])
            self.assertEqual(mark, {"set": "coin_medieval", "from_gold": 12, "units": 120000})
            # Spent down to 5 silver: a second start does not migrate again.
            conn.execute("UPDATE player SET gold = 0, purse_units = 500 WHERE id = 1")
            conn.commit()
        db.init_db()
        with connect().closing() as conn:
            row = conn.execute("SELECT gold, purse_units FROM player WHERE id = 1").fetchone()
            self.assertEqual((row["gold"], row["purse_units"]), (0, 500))

    def test_a_legacy_gold_write_is_adopted_in_units(self):
        from app import currency, purse
        from app.db import connect

        cset = currency.theme_set("coin_medieval")
        with connect().closing() as conn:
            conn.execute("UPDATE player SET gold = 12, purse_units = 120500 WHERE id = 1")
            # A tool or an old writer adds 3 gold to the gold column alone.
            conn.execute("UPDATE player SET gold = gold + 3 WHERE id = 1")
            self.assertEqual(purse.purse_units(conn, cset), 150500)
            conn.rollback()


class NewWorldStartsWithItsSet(unittest.TestCase):
    def test_start_purse_per_set(self):
        from app import currency, world
        from app.db import connect

        with connect().closing() as conn:
            currency.update_currency_config(conn, {"set": "scrip"})
            conn.commit()
        for options, set_id, units, gold, shown in (
            ({"world_style": "frontier dark fantasy"}, "coin_medieval", 120000, 12, "12 gold"),
            ({"world_style": "space frontier salvage", "tech_level": "spacefaring salvage"}, "credits", 120, 12,
             "120 credits"),
            ({"world_style": "a fallout rpg in the ruins"}, "caps", 120, 12, "120 caps"),
            ({"world_style": "frontier dark fantasy", "currency_set": "credits"}, "credits", 120, 12, "120 credits"),
        ):
            with self.subTest(set=set_id, options=options):
                # The last world's set (scrip, then each one before) is not this world's.
                world.start_playthrough({"player_name": "Wren", "start_location": "Low Gate", **options})
                with connect().closing() as conn:
                    row = conn.execute("SELECT gold, purse_units FROM player WHERE id = 1").fetchone()
                    self.assertEqual((row["purse_units"], row["gold"]), (units, gold))
                    self.assertEqual(currency.get_currency_config(conn)["set"], set_id)
                state = world.get_state()
                self.assertEqual(state["purse"]["units"], units)
                self.assertEqual(state["purse"]["set"], set_id)
                self.assertEqual(state["purse"]["long"], shown)
                self.assertEqual(state["player"]["gold"], gold)


SALE_LINE = "I sell my candle to @A for five silver; he nods, counts out five silver coins into my palm and takes the candle."
SALE_PROSE = (
    "He nods, reaching under the counter. \"Fair enough. Five silver.\" He counts out five silver coins and places "
    "them in your hand, and you hand him the candle."
)


def _play(line, prose, inventory, player, *, options=None):
    """play_turn with the draft mocked (the trade-atomic harness): the purse and the pack after it."""
    from unittest import mock

    from app import db, llm, world

    world.start_playthrough({"player_name": "Ash", "start_location": "Low Gate", "special_ability_origin": "none",
                             **(options or {})})
    with db.connect().closing() as conn:
        conn.execute("DELETE FROM inventory")
        conn.execute("DELETE FROM npcs WHERE code = 'A'")
        conn.execute("INSERT INTO npcs (code, name, location_id) SELECT 'A', 'Bartholomew', current_location_id "
                     "FROM player WHERE id = 1")
        for number, (name, qty) in enumerate(inventory, start=1):
            conn.execute("INSERT INTO inventory (code, name, quantity) VALUES (?, ?, ?)", (f"I{number}", name, qty))
        conn.commit()
    turn = {
        "scene_plan": {"goal": "act", "focus_points": []},
        "narration_segments": [{"label": "scene", "text": prose}],
        "narration": prose,
        "player": dict(player),
        "self_check": {"passed": True, "issues_found": [], "corrections_made": []},
        "turn_summary": "a beat",
        "scene_focus": "action",
        "scene_cast": {"present": [], "interacting": [], "off": []},
    }
    with mock.patch.object(world, "generate_turn", return_value=turn), \
            mock.patch.object(llm, "_chat_content", return_value="No"):
        out = world.play_turn(line)
    with db.connect().closing() as conn:
        row = conn.execute("SELECT gold, purse_units FROM player WHERE id = 1").fetchone()
        held = {str(r["name"]): int(r["quantity"] or 0) for r in conn.execute("SELECT name, quantity FROM inventory")}
    return row["purse_units"], row["gold"], held, out


class SilverReachesThePurse(unittest.TestCase):
    def test_five_silver_pays_500_units_and_the_purse_shows_it(self):
        from app import world

        units, gold, held, _out = _play(SALE_LINE, SALE_PROSE, [("candle", 1)], {"gold_band": "small"})
        self.assertEqual((units, gold, held.get("candle", 0)), (120500, 12, 0))
        purse = world.get_state()["purse"]
        self.assertEqual(purse["long"], "12 gold, 5 silver")
        self.assertEqual(purse["units"], 120500)

    def test_the_apply_reads_money_delta_and_clamps_in_units(self):
        from app import world
        from app.db import connect

        world.start_playthrough({"player_name": "Ash", "start_location": "Low Gate"})
        with connect().closing() as conn:
            world._apply_player(conn, {"money_delta": -300, "gold_delta": 0})
            self.assertEqual(conn.execute("SELECT purse_units FROM player").fetchone()[0], 119700)
            # A stale money_delta (gold_delta rewritten after it) is not used: the legacy gold is.
            world._apply_player(conn, {"money_delta": -300, "gold_delta": 2})
            self.assertEqual(conn.execute("SELECT purse_units, gold FROM player").fetchone()[:], (139700, 13))
            # Spending more than the purse holds stops at nothing.
            world._apply_player(conn, {"gold_delta": -900})
            self.assertEqual(conn.execute("SELECT purse_units, gold FROM player").fetchone()[:], (0, 0))
            conn.rollback()


class QuestRewardsPayUnits(unittest.TestCase):
    def test_a_reward_in_gold_pays_units(self):
        from app import quests, world
        from app.db import connect

        world.start_playthrough({"player_name": "Ash", "start_location": "Low Gate"})
        with connect().closing() as conn:
            conn.execute("UPDATE player SET purse_units = 120500, gold = 12 WHERE id = 1")
            qid = quests.create_quest(conn, title="Haul the nets", description="Haul the nets off the pier.",
                                      reward_gold=11, steps=[{"title": "Haul the nets", "description": "", "location_code": ""}])
            paid = quests.pay_quest_reward(conn, int(qid if isinstance(qid, int) else qid["id"]), turn=1)
            row = conn.execute("SELECT purse_units, gold FROM player").fetchone()
            self.assertEqual((row["purse_units"], row["gold"]), (230500, 23))
            self.assertEqual(paid["money_units"], 110000)
            self.assertIn("+11 gold", paid["text"])
            conn.rollback()


class TheMoneyCommand(unittest.TestCase):
    def test_render(self):
        from app import currency

        coin = currency.theme_set("coin_medieval")
        text, done = currency.render_money_commands("A fee of $69420, or $5.", coin)
        self.assertEqual(text, "A fee of 6 gold, 94 silver and 20 copper, or 5 copper.")
        self.assertEqual([d["units"] for d in done], [69420, 5])
        # The rendered words read back as the same number.
        self.assertEqual(currency.parse_amount(text, coin)["units"], 69420)
        # A decimal set's own price is no command; a credits world shows credits.
        self.assertEqual(currency.render_money_commands("$12.50", currency.theme_set("cash"))[0], "$12.50")
        self.assertEqual(currency.render_money_commands("$40", currency.theme_set("credits"))[0], "40 credits")

    def test_a_draft_with_69420_reaches_the_player_as_coins(self):
        from app.db import connect

        prose = "The clerk tallies the debt on his slate: $69420, owed by the end of the month."
        _units, _gold, _held, out = _play("I ask the clerk what I owe.", prose, [], {})
        with connect().closing() as conn:
            shown = conn.execute("SELECT content FROM journal WHERE kind = 'narration' ORDER BY id DESC LIMIT 1").fetchone()[0]
        self.assertIn("6 gold, 94 silver and 20 copper", shown)
        self.assertNotIn("$69420", shown)
        self.assertNotIn("$69420", str(out.get("narration") or ""))

    def test_the_gold_op_takes_the_command_as_units(self):
        from app import turn_dsl

        turn = turn_dsl.ops_to_turn("You pay.", turn_dsl.parse_ops("GOLD -$500"), "")
        self.assertEqual((turn["player"]["money_delta"], turn["player"]["gold_delta"]), (-500, 0))


class EveryCoinOfTheSetIsRead(unittest.TestCase):
    def test_the_readers_in_the_coin_set(self):
        from app import prose_state

        said = prose_state.stated_coin_amounts("You pay the innkeeper five silver and two copper.")
        self.assertEqual(said["paid"], [0.0502])
        self.assertEqual(prose_state.coin_mentions("forty-six gold"), [46])

    def test_a_credits_world_reads_40_credits(self):
        from app import currency, prose_state, world

        token = currency.use_set(currency.theme_set("credits"))
        try:
            self.assertEqual(prose_state.stated_coin_amounts("The broker hands you 40 credits.")["received"], [4])
            # Gold is no money here.
            self.assertEqual(prose_state.coin_mentions("five gold"), [])
            self.assertEqual(world._coin_prices_units("I sell it for 40 credits"), [40])
        finally:
            currency.reset_set(token)

    def test_a_credits_world_sale_pays_40_units(self):
        from app import currency, purse, world

        line ="I sell my scanner to @A for 40 credits; he transfers the credits to me and takes the scanner."
        prose = "Bartholomew nods and hands you 40 credits, then takes the scanner."
        units, gold, held, _out = _play(line, prose, [("scanner", 1)], {"gold_band": "small"},
                                        options={"world_style": "space frontier salvage",
                                                 "tech_level": "spacefaring salvage"})
        self.assertEqual((units, held.get("scanner", 0)), (160, 0))
        self.assertEqual(world.get_state()["purse"]["long"], "160 credits")
        self.assertEqual(purse.legacy_value(160, currency.theme_set("credits")), 16)


if __name__ == "__main__":
    unittest.main()
