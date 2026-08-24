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

import json
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
    prompt_sparks,
    search_idea_bank,
)
from app.setup_composer import empty_intent  # noqa: E402

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


class TestTheQueryIgnoresUnsetIntentSlots(unittest.TestCase):
    """`empty_intent()` fills its unset slots with words, not blanks.

    adapter_hint="default", start_power="ordinary", growth="steady". Those three
    went into the search on every cold roll, and "default ordinary steady"
    matches exactly two cards in a bank of ~292 -- so `style.low_fantasy_mud`
    and `ability.pulse_count` sat at the top of the spark list on every single
    randomization. Measured live before the fix: 10/10 rolls returned some
    spelling of "low fantasy mud and knives" as world_style, one of them the raw
    card id. After: 12/12 distinct.
    """

    def test_a_cold_intent_plan_contributes_nothing_to_the_query(self):
        plan = empty_intent("")
        query = build_query_from_setup({}, fields=STYLE_FIELDS, intent=plan)
        self.assertEqual(query.strip(), "", f"cold intent leaked {query!r} into the search")

    def test_the_specific_sentinels_are_gone(self):
        plan = empty_intent("")
        query = build_query_from_setup({}, fields=STYLE_FIELDS, intent=plan).lower()
        for sentinel in ("default", "ordinary", "steady"):
            self.assertNotIn(sentinel, query)

    def test_a_real_intent_value_still_reaches_the_query(self):
        plan = empty_intent("")
        plan["genre"] = "harbour noir"
        plan["tone"] = "steady"  # equals no default: tone's default is ""
        query = build_query_from_setup({}, fields=STYLE_FIELDS, intent=plan).lower()
        self.assertIn("harbour noir", query)
        self.assertIn("steady", query)

    def test_a_deliberate_power_fantasy_choice_still_reaches_the_query(self):
        plan = empty_intent("")
        plan["power_fantasy"] = {**plan["power_fantasy"], "start_power": "near_useless"}
        query = build_query_from_setup({}, fields=STYLE_FIELDS, intent=plan).lower()
        self.assertIn("near_useless", query)

    def test_cold_sparks_vary_when_an_intent_plan_is_passed(self):
        plan = empty_intent("")
        seen: set[str] = set()
        for _ in range(6):
            pkg = idea_sparks_for_prompt({}, fields=STYLE_FIELDS, intent=plan, limit=4)
            seen.update(s["id"] for s in pkg["sparks"])
        self.assertGreater(
            len(seen), 10, f"6 cold rolls saw only {len(seen)} distinct sparks: {sorted(seen)}"
        )


class TestScoredResultsVaryWithoutLosingRelevance(unittest.TestCase):
    """A real idea used to pin its own four cards just as hard.

    `sort(...)[:limit]` is deterministic, and a flat tie (a dozen cards all
    scoring 1.0) was broken by title, so the same alphabetical tail won forever.
    """

    QUERY = "harbour noir smugglers and customs men"
    KINDS = ["place", "style", "tone", "faction", "opening", "ability", "loot", "death"]

    def test_the_same_idea_does_not_return_one_fixed_answer(self):
        seen: set[str] = set()
        for _ in range(8):
            seen.update(c["id"] for c in search_idea_bank(self.QUERY, kinds=self.KINDS, limit=4))
        self.assertGreater(len(seen), 4, f"8 rolls of one idea saw only {sorted(seen)}")

    def test_a_flat_tie_is_not_broken_alphabetically(self):
        seen: set[str] = set()
        for _ in range(8):
            seen.update(
                c["id"]
                for c in search_idea_bank(
                    "sunken temple divers who owe a god money", kinds=self.KINDS, limit=4
                )
            )
        self.assertGreater(len(seen), 8, f"a flat-scoring query returned only {sorted(seen)}")

    def test_weak_matches_never_displace_strong_ones(self):
        # Everything returned must score at least half the best score, so a
        # 0.35 substring hit cannot push out a direct keyword match.
        for _ in range(8):
            hits = search_idea_bank(self.QUERY, kinds=self.KINDS, limit=4)
            best = max(h["score"] for h in hits)
            for hit in hits:
                self.assertGreaterEqual(hit["score"], best * 0.5, hit["id"])

    def test_relevance_survives_the_shuffle(self):
        for _ in range(8):
            hits = search_idea_bank(self.QUERY, kinds=self.KINDS, limit=4)
            blob = " ".join(f"{h['title']} {h['text']}" for h in hits).lower()
            self.assertTrue(
                any(w in blob for w in ("harbor", "harbour", "noir", "customs", "dock", "port")),
                f"a harbour-noir idea returned {[h['id'] for h in hits]}",
            )


class TestPromptSparksSendContentNotFinishedAnswers(unittest.TestCase):
    """Three spark fields are shaped exactly like a setup value, and all three
    were measured being pasted into the form verbatim:

        world_style    = "low_fantasy_mud"                     (the card id)
        tone           = "pastoral_curious"                    (the card id)
        world_style    = "Low fantasy mud and knives"           (the title)
        start_location = "a broken cart axle starts the plot"   (the examples)

    The rules block has said "do not copy titles verbatim as final values" the
    whole time and 13 verbatim titles still landed across 12 rolls, so prompts
    now carry text and keywords only. Those say the same thing without handing
    over a finished answer.
    """

    PASTEABLE = ("id", "title", "examples")

    def test_pasteable_fields_are_stripped(self):
        pkg = idea_sparks_for_prompt({}, fields=STYLE_FIELDS, limit=4)
        safe = prompt_sparks(pkg)
        self.assertTrue(safe["sparks"])
        for card in safe["sparks"]:
            for field in self.PASTEABLE:
                self.assertNotIn(field, card)

    def test_the_content_survives(self):
        pkg = idea_sparks_for_prompt({}, fields=STYLE_FIELDS, limit=4)
        safe = prompt_sparks(pkg)
        for card in safe["sparks"]:
            self.assertIn("text", card)
            self.assertIn("keywords", card)
            self.assertTrue(card["text"], "a spark reached the prompt with nothing in it")
        self.assertEqual(safe["rules"], pkg["rules"])

    def test_the_original_package_is_untouched(self):
        # The search API and the setup UI still render titles and ids.
        pkg = idea_sparks_for_prompt({}, fields=STYLE_FIELDS, limit=4)
        prompt_sparks(pkg)
        self.assertTrue(all(s.get("id") for s in pkg["sparks"]))
        self.assertTrue(all(s.get("title") for s in pkg["sparks"]))

    def test_no_id_or_title_appears_in_a_serialized_prompt(self):
        pkg = idea_sparks_for_prompt({}, fields=STYLE_FIELDS, limit=4)
        blob = json.dumps(prompt_sparks(pkg))
        for spark in pkg["sparks"]:
            self.assertNotIn(spark["id"], blob)
            self.assertNotIn(spark["title"], blob)

    def test_none_and_junk_are_handled(self):
        self.assertIsNone(prompt_sparks(None))
        self.assertEqual(prompt_sparks({"sparks": "not a list"}), {"sparks": "not a list"})


if __name__ == "__main__":
    unittest.main()
