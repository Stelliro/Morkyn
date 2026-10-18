"""8B run 148, T54 and T55: what a declared search finds in the Stormbreaker's hold.

T54: "I crawl into the hull past the broken ribs and search the hold the
salvagers left alone" found "a bundle of papers tucked beneath a collapsed
beam" on a successful roll; the gain was refused as taken without the player
asking, and the find was cut from the prose. A search of a place asks for
what it holds.

T55: "a bundle of damp paper catches your eye, and you kneel to retrieve it
... a ledger of goods and debts" came with GRANT "salvage ledger", refused as
never arriving: the find named another paper. One paper found is another.

Run:  .venv\\Scripts\\python -m unittest tests.test_8b_run148_hold
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-run148-hold-"))
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
        kept = world._filter_inventory_changes(conn, changes, narration=narration, player_input=line, rejected=rejected)
    return kept, rejected


T54_LINE = ("\"Rust and rot will do if it tells me where the cargo went.\" I crawl into the hull past the broken ribs and "
            "search the hold the salvagers left alone.")
T54_PROSE = ("You crawl into the hull, your boots scraping against the damp wood. The salvagers left this hold alone. You sift "
             "through the wreckage. You find a bundle of papers tucked beneath a collapsed beam—stained with water and ink, "
             "but legible enough to make out the name Stormbreaker scrawled across the top. You tuck them into your coat.")
T55_LINE = "I keep searching the hold, under the collapsed beam and behind the ribs, for anything the water left legible."
T55_PROSE = ("You crouch lower, brushing aside the wreckage. Beneath the debris, a bundle of damp paper catches your eye, and "
             "you kneel to retrieve it. The ink is faded, but the symbols are unmistakable—records of the wreck’s last voyage, "
             "a ledger of goods and debts, and a name that makes your breath hitch.")


class ASearchOfAPlace(unittest.TestCase):
    def test_searching_the_hold_asks_for_what_it_holds(self):
        from app.llm import player_take_intent

        self.assertTrue(player_take_intent("I crawl into the hull past the broken ribs and search the hold the salvagers left alone."))
        self.assertTrue(player_take_intent("I rummage through the chest."))

    def test_looking_for_a_person_asks_for_nothing(self):
        from app.llm import player_take_intent

        self.assertFalse(player_take_intent("I search the crowd for Eldric's face."))
        self.assertFalse(player_take_intent("I scan the horizon and wait."))

    def test_the_bundle_of_papers_found_on_the_search_arrives(self):
        _pack()
        kept, rejected = _filter([{"name": "bundle of papers", "quantity_delta": 1}], T54_PROSE, T54_LINE)
        self.assertEqual([c["name"] for c in kept], ["bundle of papers"], rejected)


class OneOfANamedThing(unittest.TestCase):
    """T56: GRANT "a bundle of papers" QTY moderate for "I take the bundle of papers and the ledger" rolled two bundles."""

    LINE = "I take the bundle of papers and the ledger, wrap them in my shirt against the damp, and climb out of the hold to Aldous."
    PROSE = ("You wrap the bundle of papers and the ledger in your linen shirt, shielding them from the damp air. You climb up "
             "the wooden planks. Aldous is waiting at the top.")

    def test_the_bundle_is_one_bundle(self):
        _pack()
        kept, rejected = _filter(
            [{"name": "a bundle of papers", "quantity_band": "moderate"}, {"name": "a ledger", "quantity_band": "small"}],
            self.PROSE, self.LINE,
        )
        self.assertEqual({c["name"]: c.get("quantity_delta") for c in kept}, {"a bundle of papers": 1, "a ledger": 1}, rejected)
        self.assertFalse(any("quantity_band" in c for c in kept))

    def test_a_plural_keeps_its_band(self):
        from app.world import _one_of_a_named_thing

        change = {"name": "arrows", "quantity_band": "moderate"}
        self.assertEqual(_one_of_a_named_thing(change, "arrows", "i gather the arrows from the straw.", ""), change)


class ThingAlreadyCarriedUnderItsMeasure(unittest.TestCase):
    """T69: GRANT "rope" for the coil of rope taken the turn before, now paid for, is no new rope."""

    LINE = "I pay the ten gold for the rope and mallet and ask Ulric which of his men will come to the wreck with me."
    PROSE = ("You hand over the ten gold, the coins clinking as they pass from your pouch to Ulric’s rough palm. He nods, "
             "the transaction sealed, and the rope and mallet you’ve paid for now rest in your gear. You ask which of his "
             "men will join you at the wreck.")

    def test_the_rope_lands_on_the_coil_row(self):
        # A rope paid for the turn after it was taken cannot be told from a second rope by the judge;
        # the write at least keeps one row for it (no "rope x1" beside "a coil of rope x1").
        from app import world
        from app.db import connect

        _pack(("a coil of rope", 1))
        kept, rejected = _filter([{"name": "rope", "quantity_delta": 1}, {"name": "mallet", "quantity_delta": 1}], self.PROSE, self.LINE)
        self.assertIn("mallet", [c["name"] for c in kept], rejected)
        with connect() as conn:
            world._apply_inventory(conn, kept)
            names = {str(r[0]) for r in conn.execute("SELECT name FROM inventory WHERE quantity > 0")}
        self.assertNotIn("rope", names)
        self.assertIn("a coil of rope", names)


class TheKeyInHandUnderANewName(unittest.TestCase):
    """8B run 149, T7: GRANT "guild key" for the tarnished key in the player's grip put a third key in the pack."""

    LINE = "\"Nothing's free with the guild, I know. What's the mark on this key, Lettice?\""
    PROSE = ("“Nothing's free with the guild, I know. What's the mark on this key, Lettice?” you ask. The key in your grip "
             "feels heavier than it should. Lettice Garner [[F]] leans in, her fingers tracing the rusted metal. \"This is a "
             "guild mark,\" she says. \"Older than most of the things you’ll find in these waters.\"")

    def test_the_key_held_is_not_a_new_key(self):
        _pack(("tarnished key", 1))
        kept, rejected = _filter([{"name": "guild key", "quantity_delta": 1}], self.PROSE, self.LINE)
        self.assertEqual(kept, [], rejected)

    def test_a_key_handed_over_is_new(self):
        _pack(("tarnished key", 1))
        prose = "Lettice Garner [[F]] presses a brass guild key into your hand. \"Show them this,\" she says."
        kept, rejected = _filter([{"name": "guild key", "quantity_delta": 1}], prose, self.LINE)
        self.assertEqual([c["name"] for c in kept], ["guild key"], rejected)


class APaperFoundUnderAnotherName(unittest.TestCase):
    def test_the_damp_paper_retrieved_is_the_ledger(self):
        from app.world import _handed_under_another_noun

        self.assertIn("salvage ledger", _handed_under_another_noun(T55_PROSE, "salvage ledger").lower())

    def test_the_ledger_arrives(self):
        _pack()
        kept, rejected = _filter([{"name": "salvage ledger", "quantity_delta": 1}], T55_PROSE, T55_LINE)
        self.assertEqual([c["name"] for c in kept], ["salvage ledger"], rejected)

    def test_a_paper_only_seen_is_not_taken(self):
        _pack()
        prose = "A sheet of parchment lies pinned under a beam, too far to reach. You leave it and climb out."
        kept, rejected = _filter([{"name": "salvage ledger", "quantity_delta": 1}], prose, T55_LINE)
        self.assertEqual(kept, [], rejected)


if __name__ == "__main__":
    unittest.main()
