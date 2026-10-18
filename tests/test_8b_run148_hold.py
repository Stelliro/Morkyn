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


class HeldIsNotGained(unittest.TestCase):
    """8B run 149, T11: "the guild's lockpicking tools clutched in your hands" put two picks nobody gave or found in the pack."""

    LINE = "I leave the tally house and walk back to the Dredges to search the main sump for the locks the guild wants."
    PROSE = ("You walk through the damp streets. The main sump, a gaping wound in the earth, awaits your descent. You pause at "
             "the edge, the guild's lockpicking tools clutched in your hands, and prepare to dive into the depths.")

    def test_tools_only_held_came_from_nowhere(self):
        _pack()
        kept, rejected = _filter([{"name": "brass lockpick", "quantity_band": "moderate"}], self.PROSE, self.LINE)
        self.assertEqual(kept, [], rejected)

    def test_tools_the_prose_hands_over_arrive(self):
        _pack()
        prose = "Lettice presses a set of brass lockpicks into your hands. \"Bring them back,\" she says."
        kept, rejected = _filter([{"name": "brass lockpick", "quantity_band": "small"}], prose, self.LINE)
        self.assertEqual([c["name"] for c in kept], ["brass lockpick"], rejected)


class TakingBackOnesOwnThing(unittest.TestCase):
    """8B run 149, T18: "You pick up the guild key from the counter" grew the guild key the player already held."""

    LINE = "I pick up the guild key from the counter and wait for Lettice to answer."
    PROSE = ("You pick up the guild key from the counter, its cold metal humming in your palm. Lettice Garner [[F]] emerges "
             "from the shadows. \"That’s not for you,\" she says. You hold the key steady, the weight of it a reminder of the "
             "debt you owe.")

    def test_the_key_picked_up_again_is_the_same_key(self):
        _pack(("guild key", 1))
        kept, rejected = _filter([{"name": "guild key", "quantity_band": "small"}], self.PROSE, self.LINE)
        self.assertEqual(kept, [], rejected)

    def test_another_key_is_a_second_key(self):
        _pack(("guild key", 1))
        prose = "You pick up another guild key from the shelf, this one newer, and pocket it beside the first."
        kept, rejected = _filter([{"name": "guild key", "quantity_delta": 1}], prose, "I pick up the other guild key from the shelf.")
        self.assertEqual([c["name"] for c in kept], ["guild key"], rejected)


class BringingUpWhateverIsThere(unittest.TestCase):
    """8B run 149, T23: the box brought up from the Dredges held coins, a compass and an envelope, all refused as taken unasked."""

    LINE = "I dive the Dredges again, deeper this time, and bring up whatever the guild's token was meant to open."
    PROSE = ("You dive the Dredges again, deeper this time. Your hand finds the object the guild's iron token was meant to open. "
             "It's a small, rusted box, its surface worn and its lock stiff with age. You surface and make your way to the "
             "shore. You pry it open with your brass lockpick, and inside you find a collection of old coins, a broken compass, "
             "and a single, unmarked envelope.")

    def test_bringing_up_whatever_asks_for_it(self):
        from app.llm import player_take_intent

        self.assertTrue(player_take_intent(self.LINE))

    def test_the_compass_and_the_envelope_arrive(self):
        _pack()
        kept, rejected = _filter(
            [{"name": "broken compass", "quantity_delta": 1}, {"name": "unmarked envelope", "quantity_delta": 1}],
            self.PROSE, self.LINE,
        )
        self.assertEqual([c["name"] for c in kept], ["broken compass", "unmarked envelope"], rejected)


class HandedOverIsGone(unittest.TestCase):
    """8B run 149, T21 and T32: things the player handed to Lettice were granted to the player."""

    def test_the_cases_handed_over_are_not_gained(self):
        _pack()
        line = "\"Two more boxes, then. Lettice, mark this one against my name before I go.\""
        prose = ("You hand over the two remaining wooden cases to Lettice Garner [[F]], their surfaces dented and stained with "
                 "brine. She takes them with a practiced flick of her wrist. \"Marked,\" she says. You feel the weight of the two "
                 "cases in your hands, a reminder that the work isn’t done yet.")
        kept, rejected = _filter([{"name": "Wooden Case", "quantity_band": "moderate"}], prose, line)
        self.assertEqual(kept, [], rejected)

    def test_the_token_handed_over_is_not_gained(self):
        _pack()
        line = "\"Three silver I can find. Lettice, will you take the coin and the token from me and write the credit cleared?\""
        prose = ("You hand over the three silver coins and the iron token to Lettice, who takes them with a practiced nod. "
                 "She flips the token over in her palm, then tucks it into a leather-bound ledger.")
        kept, rejected = _filter([{"name": "iron token", "quantity_delta": 1}], prose, line)
        self.assertEqual(kept, [], rejected)

    def test_a_thing_handed_to_the_player_still_arrives(self):
        _pack()
        prose = "Lettice hands you the iron token across the counter. \"Keep it,\" she says."
        kept, rejected = _filter([{"name": "iron token", "quantity_delta": 1}], prose, "\"What do I owe?\"")
        self.assertEqual([c["name"] for c in kept], ["iron token"], rejected)


class ALidRevealsAFind(unittest.TestCase):
    """8B run 149, T34: the map the lid revealed was refused, under a description for a name."""

    LINE = "I search the Dredges' wreckage for the second of the guild's boxes."
    PROSE = ("You kneel among the tangled wreckage, fingers brushing over rusted gears. The light catches on the brass hinges of "
             "the second of the guild’s locked cases. A faint creak echoes as you pry open the lid, revealing a single, weathered "
             "map inside—marked with symbols you don’t recognize.")

    def test_the_revealed_map_is_found(self):
        _pack()
        kept, rejected = _filter([{"name": "map with unknown symbols and a destination marked", "quantity_band": "moderate"}], self.PROSE, self.LINE)
        self.assertEqual(len(kept), 1, rejected)

    def test_a_description_is_cut_to_its_name(self):
        from app.world import _sanitize_item_name

        self.assertEqual(_sanitize_item_name("map with unknown symbols and a destination marked"), "map")
        self.assertEqual(_sanitize_item_name("mother's brass tide-reckoner"), "mother's brass tide-reckoner")
        self.assertEqual(_sanitize_item_name("coil of rope"), "coil of rope")


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
