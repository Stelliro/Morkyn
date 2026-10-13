"""7B run 10 (Qwen2.5 7B on MLE, agent as player): owned things, plurals, skill gains, the giver's stock."""
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-7b-run10-items-"))
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


def _pack(*names):
    from app.db import connect, init_db

    init_db()
    with connect() as conn:
        conn.execute("DELETE FROM inventory")
        for name, qty in names:
            conn.execute("INSERT INTO inventory (name, quantity) VALUES (?, ?)", (name, qty))


def _filter(changes, narration, line):
    from app import world
    from app.db import connect

    rejected: list = []
    with connect() as conn:
        kept = world._filter_inventory_changes(
            conn, changes, narration=narration, player_input=line, rejected=rejected
        )
    return kept, rejected


class HerOwnReckoner(unittest.TestCase):
    """T1: GRANT "reckoner" for the reckoner she already owns made a second one."""

    NARRATION = (
        "Jehane Tully, a knife grinder, stands by the forge entrance. You reach into your shirt, "
        "pulling out the small, worn reckoner. \"But I'll sharpen your knives. How many, and what does it pay?\""
    )
    LINE = "\"The reckoner isn't for trade.\" I put it back inside my shirt. \"But I'll sharpen your knives.\""

    def test_no_second_reckoner(self):
        _pack(("mother's brass tide-reckoner", 1))
        kept, rejected = _filter([{"name": "reckoner", "quantity_delta": 1}], self.NARRATION, self.LINE)
        self.assertEqual(kept, [])
        self.assertEqual(rejected, [], "her own thing is not a refused gain: nothing to trim")

    def test_one_handed_over_is_new(self):
        _pack(("mother's brass tide-reckoner", 1))
        kept, _ = _filter(
            [{"name": "reckoner", "quantity_delta": 1}],
            "Jehane hands you a battered reckoner of her own. \"Take it, it was my father's.\"",
            "I ask whether she has a spare.",
        )
        self.assertEqual([c["name"] for c in kept], ["reckoner"])


class PluralsAndSynonyms(unittest.TestCase):
    def test_tokens(self):
        from app.world import _item_name_tokens, _sentence_mentions_item

        self.assertEqual(_item_name_tokens("knives")[-1], "knife")
        self.assertTrue(_sentence_mentions_item("i set the knives back on her bench", "sharpened blade",
                                                _item_name_tokens("sharpened blade")))
        self.assertTrue(_sentence_mentions_item("the old lamp", "lantern", _item_name_tokens("lantern")))
        self.assertFalse(_sentence_mentions_item("a coil of wire", "rope", _item_name_tokens("rope")))

    def test_give_back_with_the_pack_name(self):
        from app import world
        from app.db import connect

        _pack(("Sharpened blade", 5))
        with connect() as conn:
            removed = world._remove_shown_gives(
                conn,
                [],
                "You set the sharpened and polished knives back on Jehane's bench, giving them a final glance.",
                "I set the knives back on her bench. \"These are yours, not mine.\"",
            )
        self.assertEqual([(c["name"], c["quantity_delta"]) for c in removed], [("Sharpened blade", -5)])


class SkillGainsNeedUse(unittest.TestCase):
    """T7: holding out a hand paid sleight of hand +2."""

    def test_dropped_when_not_used(self):
        from app.world import _gate_model_skill_gains

        result = {"skill_changes": [{"name": "sleight_of_hand", "delta": 2}]}
        dropped = _gate_model_skill_gains(
            result, "I hold out my open hand and don't move. \"Earned it, yes. So put the gold in my hand, Jehane.\""
        )
        self.assertEqual(len(dropped), 1)
        self.assertEqual(result["skill_changes"], [])

    def test_kept_when_used_or_trained_or_engine(self):
        from app.world import _gate_model_skill_gains

        for line, change in (
            ("I salvage what I can from the hull.", {"name": "Salvage", "delta": 1}),
            ("I read the tide against the reckoner.", {"name": "Tide-reading", "delta": 1}),
            ("I practise palming the coin until it vanishes.", {"name": "sleight_of_hand", "delta": 1}),
            ("I hold out my hand.", {"name": "sleight_of_hand", "delta": 1, "_engine_practice": True}),
        ):
            result = {"skill_changes": [change]}
            self.assertEqual(_gate_model_skill_gains(result, line), [], line)
            self.assertEqual(result["skill_changes"], [change])


class TheGiversStock(unittest.TestCase):
    """T5: Jehane handed the knives Isk sharpened for her back, and five blades went into the pack."""

    NARRATION = (
        "You sit down at Jehane Tully's spare whetstone and begin sharpening the first knife. Jehane returns "
        "with the polished blades, handing them to you with a smile. \"Done,\" she says. You take the sharpened blades."
    )
    LINE = "\"Deal.\" I sit down at her spare whetstone and start on the knives, one after another."

    def test_it_takes_is_not_the_player_taking(self):
        from app.llm import player_take_intent

        self.assertFalse(player_take_intent(self.LINE + " working each edge until it takes a hair off my arm."))
        self.assertTrue(player_take_intent("He takes the coin; I take the lamp."))

    def test_not_hers(self):
        _pack()
        kept, rejected = _filter([{"name": "Sharpened blade", "quantity_delta": 5}], self.NARRATION, self.LINE)
        self.assertEqual(kept, [])
        self.assertEqual([r["name"] for r in rejected], ["Sharpened blade"])

    def test_a_real_gift_still_passes(self):
        _pack()
        kept, _ = _filter(
            [{"name": "whetstone", "quantity_delta": 1}],
            "Jehane hands you a small whetstone. \"Keep it. You've a good hand for an edge.\"",
            "I finish the last knife and set it on the rack.",
        )
        self.assertEqual([c["name"] for c in kept], ["whetstone"])

    def test_own_work_handed_back_passes(self):
        _pack()
        kept, _ = _filter(
            [{"name": "mended net", "quantity_delta": 1}],
            "The old woman hands you the mended net.",
            "I ask her to mend my net and wait.",
        )
        self.assertEqual([c["name"] for c in kept], ["mended net"])


if __name__ == "__main__":
    unittest.main()
