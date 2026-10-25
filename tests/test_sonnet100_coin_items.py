"""F194 (sonnet100, Hermes 3 8B played by Sonnet, 2026-10-25): a coin amount or a band label filed as an item.

T68: GRANT "eighty silver" for "He opens a drawer and counts out eighty silver from his stash" put
"eighty silver x1" in the pack, rolled an item die item:eighty silver, and left the purse unchanged.
T19: GRANT "leather pouch of gold" for "He hands over a single dull copper coin, and the leather pouch
of gold" put "leather pouch of gold x1" in the pack.
T13: the draft split one TAKE over three lines ('TAKE: "brass medallion"', 'TAKE: "QTY: 1"',
'TAKE: "BAND: small"') and "BAND: small x1" was filed beside the medallion, with a die item:BAND: small.
T14: 'GRANT: brass medallion QTY:1 BAND:small' (no quotes) kept "brass" as the name and read
"medallion" as its amount; "brass x1" was filed with nothing brass found or taken.
The candle (T56, taken as asked) and the reeve's crest medallion (T60, found on the body) were
granted right and still are.

The decision is made once, in world._not_a_thing_name, asked where a name becomes a gain
(_filter_inventory_changes for the draft's ops and ground_acquisitions' finds, _grant_shown_takes for
takes the prose shows; resolve_turn_bands asks it first so such a name gets no item die): a phrase
headed by a coin word, a band label or an op label, or a bare metal is money or nothing. The head
noun decides, so real things with those words keep granting. Money is noted for the transaction
parser (m0) and not paid here. The op parser (turn_dsl) reads the T13 and T14 op lines right too.

Run:  cd tests && ../.venv/bin/python -m unittest test_sonnet100_coin_items
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-sonnet100-coin-items-"))
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


def _recorded(fn):
    """Run fn inside a turn ledger and return (its result, the ledger's notes)."""
    from app import turn_ledger

    notes: list[dict] = []

    @turn_ledger.recorded("test")
    def go():
        out = fn()
        notes.extend(turn_ledger.current().notes)
        return out

    return go(), notes


def _filter(changes, narration, line):
    from app import world
    from app.db import connect

    def run():
        with connect().closing() as conn:
            conn.execute("DELETE FROM inventory")
            return world._filter_inventory_changes(conn, changes, narration=narration, player_input=line)

    return _recorded(run)


def _grant(name, band="small"):
    return {"name": name, "quantity_band": band, "item_type": "misc"}


def _take(name, band="-trivial"):
    return {"name": name, "quantity_band": band, "item_type": "misc"}


T68_LINE = "I say I will take the eighty silver now, in coin, not a claim, and ask @F to mark my salvage job as delivered."
T68_PROSE = (
    "Eadric [[F]] looks up from the salvage claim he's writing. \"Ah, Isk, I see you've brought what we discussed to the "
    "guild. Good, good.\" He sets down his quill and folds his hands on the paper before him. \"I trust you're satisfied "
    "with the eighty silver I've marked against your salvage job? It's the price agreed upon with the guild's tallymen, "
    "and I've written you a claim to show for it. You'll be paid eighty silver once the salvage sells, minus our twenty "
    "percent handling fee.\"\n\nYou insist that you'd prefer to take the eighty silver now in coin, not a claim. \"I've got "
    "expenses, Eadric. I'd rather have the silver directly. Is it possible?\"\n\nEadric [[F]] considers this for a moment. "
    "\"Very well, Isk. But I must warn you, taking eighty silver in coin now will delay your payment from future salvage. "
    "We'll mark it against your account, but you'll need to settle with the guild directly before we'll give you coin.\" "
    "He opens a drawer and counts out eighty silver from his stash. \"Here you go then. Eighty silver. But make sure "
    "you're good with us before you come looking for more coin, eh?\""
)
T19_LINE = "I tell @E I dug it out of the mud in the drowned lower district this morning, and I ask what he'll pay for it."
T19_PROSE = (
    "The trader, a middle-aged man with a weathered look, raises an eyebrow at you.\n\nYou tell him you dug it out of the "
    "mud in the drowned lower district [[L4]] this morning, and ask what he'll pay for it. The trader frowns, turning the "
    "medallion over in his fingers. \"It's a piece of the old harbour, I reckon. Salvage value to someone, maybe. I could "
    "offer you a copper for it, if you're desperate.\"\n\nThe medallion is heavy in your hand, and the trader's offer is "
    "small, but it would be something. \"A copper, then. It's a start.\"\n\nThe trader nods, reaching for a small leather "
    "pouch. \"Aye, that'll be 1 gold.\" He hands over a single dull copper coin, and the leather pouch of gold. \"Try the "
    "guild. They might have more use for old harbour salvage than I do.\"\n\nYou take the copper and the gold, tucking "
    "them away with a nod of thanks."
)
T13_LINE = "I head down to the drowned lower district and start picking through the mud and rubble for anything worth salvaging."
T13_PROSE = (
    "You head down to the drowned lower district and start picking through the mud and rubble for anything worth "
    "salvaging. The sea has left behind a sad jumble of broken things. There are a few battered barrels, some splintered "
    "beams, and heaps of smashed pottery. You dig your fingers into the sludge, searching for anything of value. A few "
    "pieces of brass, copper, and broken glass glint up at you. You could spend the morning sifting through these ruins. "
    "Saltmarrow [[L1]]'s harbor is long gone, but this area is still a rich patchwork of ancient refuse.\n\nYou find a "
    "small brass medallion with strange runes on it. It looks like something from a very old faith. There are worse ways "
    "to spend a morning."
)
T13_OPS = (
    "===NAR===\n" + T13_PROSE + "\n===OPS===\n"
    'TAKE: "brass medallion"\nTAKE: "QTY: 1" \nTAKE: "BAND: small"\nGOLD: "0"\n'
)
T14_LINE = "I climb back up to #L1 and look for a trader in the market who'll buy a brass medallion."
T14_PROSE = (
    "You climb back up to Saltmarrow [[L1]] and make your way to the market square. The sun is still low in the sky as "
    "you search for a trader who might be interested in the brass medallion you found. You approach the first vendor you "
    "see, a reeve's deputy with a table of salvaged goods.\n\n\"Salvage for sale, friend,\" the deputy says with a nod. "
    "\"What have you got there?\"\n\nYou show them the medallion. \"Looking to buy this. Might be worth something.\"\n\n"
    "They take the medallion and turn it over in their gloved hand. \"I'll give you 2 silver for it, friend. That's a "
    "fair price for scrap.\""
)
T14_OPS = "===NAR===\n" + T14_PROSE + "\n===OPS===\nGRANT: brass medallion QTY:1 BAND:small\nGOLD: -4\n"
T68_OPS = (
    "===NAR===\n" + T68_PROSE + "\n===OPS===\n"
    'GRANT: "eighty silver" "small" "coin"\nTAKE: "salvage job claim" "1" "delivered"\nGOLD: "0"\n'
)


class NamesThatAreNoThing(unittest.TestCase):
    """The one decision: what the recorded names are read as, and what stays a thing."""

    def test_the_recorded_names_are_money_or_nothing(self):
        from app.world import _not_a_thing_name

        verdicts = {
            name: (_not_a_thing_name(name) or {}).get("decision")
            for name in ("eighty silver", "leather pouch of gold", "BAND: small", "brass")
        }
        self.assertEqual(verdicts, {
            "eighty silver": "coin_amount_not_an_item",
            "leather pouch of gold": "coin_amount_not_an_item",
            "BAND: small": "band_label_not_an_item",
            "brass": "material_not_an_item",
        })

    def test_the_coin_note_carries_the_amount_for_the_transaction_parser(self):
        from app.world import _not_a_thing_name

        verdict = _not_a_thing_name("eighty silver")
        self.assertEqual(verdict["amount"], "eighty silver")
        self.assertEqual(verdict["coin"], "silver")
        # m1 (2026-10-25): the note names the sum in base units of the world's set (eighty silver = 8000
        # copper); the purse is still not moved here.
        self.assertEqual(verdict["units"], 8000)

    def test_coin_heads_and_containers_of_coin(self):
        from app.world import _not_a_thing_name

        for name in ("stack of silvers", "pieces of silver", "a single dull copper coin", "purse of coppers",
                     "twenty-five gold"):
            self.assertEqual((_not_a_thing_name(name) or {}).get("decision"), "coin_amount_not_an_item", name)

    def test_band_words_and_label_fragments(self):
        from app.world import _not_a_thing_name

        for name in ("small", "moderate", "BAND", "QTY: 1", "NAME: Beth", "band: small"):
            self.assertEqual((_not_a_thing_name(name) or {}).get("decision"), "band_label_not_an_item", name)

    def test_the_head_noun_decides_so_real_things_stay_things(self):
        from app.world import _not_a_thing_name

        for name in ("brass medallion", "silver pendant", "gold ring", "copper kettle", "iron key", "leather purse",
                     "worn seagull coin", "rope", "salvage job claim", "a folded note", "bundle of herbs", "brass fitting",
                     "bar of silver", "jeweled crown", "gold-threaded cloak", "small leather purse", "stone",
                     "reeve's crest medallion", "candle"):
            self.assertIsNone(_not_a_thing_name(name), name)

    def test_counted_gold_coins_keep_the_purse_path(self):
        """_coins_to_gold already pays these into the purse; the new decision leaves them to it."""
        from app.world import _coin_name_match, _not_a_thing_name

        for name in ("Five gold coins", "copper", "scattered coins", "copper coin", "two gold coins, none", "some silver", "silver crown"):
            self.assertTrue(_coin_name_match(name), name)
            self.assertIsNone(_not_a_thing_name(name), name)


class T68EightySilverIsNotAnItem(unittest.TestCase):
    def test_the_grant_is_dropped_with_the_coin_note(self):
        kept, notes = _filter([_grant("eighty silver"), _take("salvage job claim")], T68_PROSE, T68_LINE)
        self.assertNotIn("eighty silver", [c["name"] for c in kept])
        coin = [n for n in notes if n["decision"] == "coin_amount_not_an_item"]
        self.assertEqual(len(coin), 1, notes)
        self.assertEqual(coin[0]["item"], "eighty silver")
        self.assertEqual(coin[0]["amount"], "eighty silver")

    def test_no_item_die_is_rolled_for_the_coin(self):
        from app import world
        from app.db import connect
        from app.turn_dsl import parse_dsl_turn

        turn = parse_dsl_turn(T68_OPS, player_input=T68_LINE)
        self.assertIn("eighty silver", [c["name"] for c in turn["inventory_changes"]], "the draft's op parses as before")
        with connect().closing() as conn:
            report = world.resolve_turn_bands(conn, turn, turn=70, options={}, player_input=T68_LINE)
        tags = [r.get("tag") for r in report.get("rolls") or []]
        self.assertNotIn("item:eighty silver", tags, tags)
        self.assertNotIn("item:eighty silver", [str(line) for line in report.get("lines") or []])


class T19PouchOfGoldIsNotAnItem(unittest.TestCase):
    def test_the_pouch_of_gold_is_dropped_with_the_coin_note(self):
        kept, notes = _filter([_take("copper coin", "none"), _grant("leather pouch of gold")], T19_PROSE, T19_LINE)
        self.assertEqual([c["name"] for c in kept if int(c.get("quantity_delta") or 0) > 0], [],
                         "neither the coin nor the pouch of gold is a row")
        coin = [n for n in notes if n["decision"] == "coin_amount_not_an_item"]
        self.assertEqual([n["item"] for n in coin], ["leather pouch of gold"], notes)
        self.assertEqual(coin[0]["coin"], "gold")


class T13BandLabelIsNotAnItem(unittest.TestCase):
    def test_the_split_take_parses_to_one_item(self):
        """'TAKE: "BAND: small"' is the band's label, not a thing called "BAND: small"."""
        from app.turn_dsl import parse_dsl_turn

        turn = parse_dsl_turn(T13_OPS, player_input=T13_LINE)
        self.assertEqual([c["name"] for c in turn["inventory_changes"]], ["brass medallion"])

    def test_the_label_never_reaches_the_pack_and_the_medallion_does(self):
        """Even arriving as a name (an older draft), the label is dropped and the medallion still grants."""
        kept, notes = _filter([_take("brass medallion"), _take("BAND: small")], T13_PROSE, T13_LINE)
        self.assertEqual([c["name"] for c in kept], ["brass medallion"])
        self.assertGreater(int(kept[0]["quantity_delta"]), 0, "the medallion found and taken is a gain, as before")
        self.assertEqual([n["item"] for n in notes if n["decision"] == "band_label_not_an_item"], ["BAND: small"])

    def test_no_item_die_for_the_label(self):
        from app import world
        from app.db import connect

        turn = {"inventory_changes": [_grant("BAND: small"), _grant("brass medallion")]}
        with connect().closing() as conn:
            report = world.resolve_turn_bands(conn, turn, turn=14, options={}, player_input=T13_LINE)
        tags = [r.get("tag") for r in report.get("rolls") or []]
        self.assertNotIn("item:BAND: small", tags, tags)
        self.assertIn("item:brass medallion", tags, tags)


class T14BrassIsNotAnItem(unittest.TestCase):
    def test_the_glued_labels_are_fields(self):
        """'GRANT: brass medallion QTY:1 BAND:small': QTY:1 is the amount (it was a word of the name before).
        The unquoted name still parses as its first word, "brass" (the medallion is already held: reading
        the whole name would grant a second one, which the grounding gate lets through), and "brass" alone
        is dropped below."""
        from app.turn_dsl import parse_dsl_turn

        turn = parse_dsl_turn(T14_OPS, player_input=T14_LINE)
        changes = turn["inventory_changes"]
        self.assertEqual([c["name"] for c in changes], ["brass"])
        self.assertEqual(changes[0].get("quantity_delta"), 1)

    def test_a_bare_material_word_is_dropped(self):
        kept, notes = _filter([_grant("brass")], T14_PROSE, T14_LINE)
        self.assertEqual(kept, [])
        self.assertEqual([n["item"] for n in notes if n["decision"] == "material_not_an_item"], ["brass"])

    def test_the_quoted_forms_still_parse(self):
        from app.turn_dsl import parse_dsl_turn

        turn = parse_dsl_turn("===NAR===\nx\n===OPS===\nGRANT rope QTY small\nTAKE boots BAND -small\n", player_input="I go")
        self.assertEqual(
            [(c["name"], c.get("quantity_band")) for c in turn["inventory_changes"]],
            [("rope", "small"), ("boots", "-small")],
        )


T56_LINE = "I hand the peddler two copper and take the candle."
T56_PROSE = (
    "The trader, Stephen [[E]], eyes the money and nods. \"Two copper will get you a candle,\" he says, \"But I've got "
    "finer wares if you've got more to spend.\"\n\nAs you reach for the candle, a peddler steps in from the foggy street. "
    "She's not one of the storekeepers, but a peddler come out of the ruins to trade.\n\n\"Two copper,\" she says, holding "
    "up a small wax candle. \"One copper to light your way. The other buys you a little warmth at your hearth.\"\n\nYou "
    "choose the peddler's candle and tuck it into your tunic. Stephen [[E]] watches, saying nothing. The peddler smiles "
    "and steps out into the fog."
)
T60_LINE = "I turn back to the body in the doorway, kneel, and search its coat and boots for a name, a mark or a purse."
T60_PROSE = (
    "You kneel and search the body, turning over its coat and boots. It wears no mark that I can see - just a tattered "
    "cloak and patched boots. But you find a small leather purse. You open it and find a silver medallion with the image "
    "of a reeve's crest stamped upon it. You don't recognize the name on the body, but the reeve's deputy Elric [[D]] might."
)


class RealThingsStillGrant(unittest.TestCase):
    """The candle and the medallion of the run, and things named with a coin word as a modifier."""

    def test_t60_the_medallion_found_on_the_body_is_granted(self):
        kept, notes = _filter([_grant("reeve's crest medallion")], T60_PROSE, T60_LINE)
        self.assertEqual([c["name"] for c in kept], ["reeve's crest medallion"], notes)

    def test_t56_the_candle_taken_as_asked_is_granted(self):
        from app import world
        from app.db import connect

        def run():
            with connect().closing() as conn:
                conn.execute("DELETE FROM inventory")
                kept = world._filter_inventory_changes(conn, [], narration=T56_PROSE, player_input=T56_LINE)
                return world._grant_shown_takes(conn, kept, T56_PROSE, T56_LINE, rejected=[])

        added, notes = _recorded(run)
        self.assertTrue([c for c in added if c["name"].endswith("candle")], (added, notes))
        self.assertFalse([n for n in notes if n["decision"].endswith("_not_an_item")], notes)

    def test_a_coin_word_as_a_modifier_keeps_the_thing(self):
        line = "I take the silver ring and the copper kettle from the shelf."
        prose = "You take the silver ring and the copper kettle from the shelf and stow them in your pack."
        kept, notes = _filter([_grant("silver ring"), _grant("copper kettle")], prose, line)
        self.assertEqual(sorted(c["name"] for c in kept), ["copper kettle", "silver ring"], notes)


class T19TheShownTakeOfCoinIsMoney(unittest.TestCase):
    def test_the_prose_take_of_the_gold_files_no_row(self):
        """'You take the copper and the gold' read by _grant_shown_takes: coin, not a thing."""
        from app import world
        from app.db import connect

        line = "I take the coins he offers and the pouch of gold."
        prose = "He hands over a single dull copper coin. You take the eighty silver and the leather pouch of gold."

        def run():
            with connect().closing() as conn:
                conn.execute("DELETE FROM inventory")
                return world._grant_shown_takes(conn, [], prose, line, rejected=[])

        added, notes = _recorded(run)
        names = [c["name"] for c in added]
        self.assertNotIn("eighty silver", names, notes)
        self.assertFalse([n for n in names if "pouch of gold" in n], notes)


if __name__ == "__main__":
    unittest.main()
