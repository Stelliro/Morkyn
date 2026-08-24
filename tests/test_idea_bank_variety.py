"""Regression tests: randomize twice, get two different worlds.

Measured live: ten "world" randomizations produced the same `world_style` nine
times -- "Post-magic wasteland", with tone "Intimate close" and custom style
"Glow means leave". Those three strings are the title and example of two cards
in `config/idea_bank/`, copied verbatim despite the spark rules telling the
model not to.

Two stacked causes, both here:

1. `build_query_from_setup` appended the FIELD NAME to the search query
   (`f.replace("_", " ")`), so a cold randomize searched the bank for
   "world style tone custom style". The literal word "tone" matches every
   `tone.*` card, so all five sparks came back as tone cards -- and the
   world_style field got no style spark at all. Relevance by field is already
   handled by `kinds_for_field()`.

2. `search_idea_bank`'s no-query branch promised "a small random-ish slice"
   and returned `pool[:limit]` -- the first N cards in load order. It was also
   guarded by `and not kind and not kinds`, which made its own kind-filtering
   unreachable, so a call WITH kinds fell through to the scoring loop and
   matched nothing at all.

Net effect: the same 5 cards out of 292, on every call, forever.

Run:  python -m unittest tests.test_idea_bank_variety
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-ideabank-test-"))
_ENV = {
    "AI_RPG_DB": str(_TMP / "world.db"),
    "AI_RPG_PACK_DIR": str(_TMP / "packs"),
    "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
    "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
    "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
    "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
}
os.environ.update(_ENV)

from app.idea_bank import (  # noqa: E402
    build_query_from_setup,
    idea_sparks_for_prompt,
    load_idea_cards,
    search_idea_bank,
)

STYLE_FIELDS = ["world_style", "tone", "custom_style"]


class TestTheQueryCarriesContentNotFieldNames(unittest.TestCase):
    def test_a_cold_setup_does_not_search_for_its_own_field_names(self):
        query = build_query_from_setup({}, fields=STYLE_FIELDS)
        for name in ("world style", "custom style", "tone"):
            self.assertNotIn(name, query.lower(), f"field name {name!r} leaked into the query")

    def test_the_player_idea_still_drives_the_query(self):
        query = build_query_from_setup(
            {"_randomize_idea": "sunken temple divers who owe a god money"},
            fields=STYLE_FIELDS,
        )
        self.assertIn("sunken temple", query.lower())

    def test_existing_field_values_still_drive_the_query(self):
        query = build_query_from_setup({"world_style": "harbour noir"}, fields=STYLE_FIELDS)
        self.assertIn("harbour noir", query.lower())


class TestNoQuerySelectionIsActuallyVaried(unittest.TestCase):
    def test_the_bank_is_big_enough_for_this_to_matter(self):
        self.assertGreater(len(load_idea_cards()), 50)

    def test_repeated_calls_do_not_return_one_fixed_slice(self):
        seen: set[str] = set()
        for _ in range(8):
            for card in search_idea_bank("", kinds=["style", "tone", "place"], limit=5):
                seen.add(card["id"])
        self.assertGreater(
            len(seen), 10, f"only {len(seen)} distinct cards over 8 calls -- selection is stuck"
        )

    def test_kind_filtering_works_in_the_no_query_branch(self):
        # This code was unreachable: the branch required `not kinds`.
        for card in search_idea_bank("", kinds=["place"], limit=6):
            self.assertEqual(card["kind"], "place")

    def test_a_call_with_kinds_returns_something(self):
        # It used to fall through to the scoring loop and match nothing.
        self.assertTrue(search_idea_bank("", kinds=["style"], limit=5))

    def test_exclusions_are_honoured(self):
        first = search_idea_bank("", kinds=["style"], limit=4)
        excluded = [c["id"] for c in first]
        again = search_idea_bank("", kinds=["style"], limit=4, exclude_ids=excluded)
        self.assertFalse({c["id"] for c in again} & set(excluded))


class TestSparksVaryBetweenRandomizations(unittest.TestCase):
    def test_two_cold_randomizations_do_not_see_the_same_sparks(self):
        runs = [
            [s["id"] for s in idea_sparks_for_prompt({}, fields=STYLE_FIELDS, limit=5)["sparks"]]
            for _ in range(6)
        ]
        distinct = {i for run in runs for i in run}
        self.assertGreater(
            len(distinct), 10,
            f"6 randomizations saw only {len(distinct)} distinct sparks: {sorted(distinct)}",
        )

    def test_sparks_are_still_produced_at_all(self):
        sparks = idea_sparks_for_prompt({}, fields=STYLE_FIELDS, limit=5)["sparks"]
        self.assertTrue(sparks, "a cold randomize got no idea sparks whatsoever")

    def test_a_real_idea_still_steers_selection(self):
        # Variety must not cost relevance: a stated idea should still win.
        sparks = idea_sparks_for_prompt(
            {"_randomize_idea": "harbour noir smugglers and customs men"},
            fields=STYLE_FIELDS,
            limit=6,
        )["sparks"]
        blob = " ".join(
            f"{s.get('title')} {s.get('text')} {' '.join(s.get('keywords') or [])}" for s in sparks
        ).lower()
        self.assertTrue(
            any(word in blob for word in ("harbor", "harbour", "smuggl", "noir", "dock", "port")),
            f"a harbour-noir idea returned unrelated sparks: {[s['id'] for s in sparks]}",
        )


if __name__ == "__main__":
    unittest.main()
