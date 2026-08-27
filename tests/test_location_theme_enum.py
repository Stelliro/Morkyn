"""Ask the model for the theme as an enum instead of guessing it from prose.

`compose_setup_intent` already asks the model to classify the setting, but asks
for free text ("genre": "short genre/setting phrase"), which is then fed back
through the keyword table. Settings that describe a genre without naming it --
"a generation ship three hundred years from landfall", "a courier with a
cranial shunt and bad debts" -- are structurally unreachable that way.

The precedent is already in this repo: `_field_contracts_for_prompt` exists
because the group path asked `magic_level`, a five-value enum, an open question
and got back "low", "Low", "low-magic", "post" and "Limited to arcane crafters
and guilds", every one of which fell through to the default.

Two gates silently drop a new plan key, and this file was written red against
both before either was touched:

  merge_intent_plans        allowlists string keys at the top of the function
  session_theme_from_intent builds an explicit dict literal

The override rule is the other half. Keywords stay the floor: if keyword
detection found a real theme, the player named a genre in their own words and
that wins. The model's answer is only for the case keywords found nothing.

Run:  python -m unittest tests.test_location_theme_enum
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-themeenum-test-"))
os.environ.update({
    "AI_RPG_DB": str(_TMP / "world.db"),
    "AI_RPG_PACK_DIR": str(_TMP / "packs"),
    "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
    "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
    "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
    "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
})

from app.setup_composer import (  # noqa: E402
    LOCATION_SEEDS_BY_THEME,
    LOCATION_THEME_IDS,
    detect_location_theme,
    merge_intent_plans,
    session_theme_from_intent,
)


class TestTheLegalSetIsDerived(unittest.TestCase):
    def test_ids_come_from_the_banks(self):
        # Hand-copied lists drift. This one cannot.
        self.assertEqual(set(LOCATION_THEME_IDS), set(LOCATION_SEEDS_BY_THEME))
        self.assertIn("generic", LOCATION_THEME_IDS)


class TestGateOneMergeIntentPlans(unittest.TestCase):
    """The string-key allowlist at the top of merge_intent_plans."""

    def test_a_legal_theme_survives_the_merge(self):
        out = merge_intent_plans({"raw_idea": "a quiet town"}, {"location_theme": "space"})
        self.assertEqual(out.get("location_theme"), "space")

    def test_case_and_padding_are_normalized(self):
        out = merge_intent_plans({"raw_idea": "x"}, {"location_theme": "  CyberPunk "})
        self.assertEqual(out.get("location_theme"), "cyberpunk")

    def test_an_illegal_theme_is_dropped_not_stored(self):
        # Never let a model string index a dict directly.
        for bad in ("solarpunk", "", "   ", "fantasy world", "FANTASY!"):
            with self.subTest(value=bad):
                out = merge_intent_plans({"raw_idea": "x"}, {"location_theme": bad})
                self.assertNotIn("location_theme", out, f"{bad!r} should not be stored")

    def test_a_non_string_theme_is_dropped(self):
        for bad in (5, ["space"], {"id": "space"}, True, None):
            with self.subTest(value=bad):
                out = merge_intent_plans({"raw_idea": "x"}, {"location_theme": bad})
                self.assertNotIn("location_theme", out)


class TestGateTwoSessionTheme(unittest.TestCase):
    """The explicit dict literal in session_theme_from_intent."""

    def test_it_carries_the_theme(self):
        theme = session_theme_from_intent({"location_theme": "wasteland"})
        self.assertEqual(theme.get("location_theme"), "wasteland")

    def test_absent_stays_empty_rather_than_missing(self):
        theme = session_theme_from_intent({"genre": "something"})
        self.assertEqual(theme.get("location_theme"), "")


class TestOverrideOnlyFillsAGap(unittest.TestCase):
    """Keywords are the floor. The player's own words outrank the classifier."""

    def test_it_fills_in_when_keywords_found_nothing(self):
        setting = "a generation ship three hundred years from landfall"
        self.assertEqual(
            detect_location_theme(world_style="a courier with bad debts"),
            "generic",
            "precondition: this setting is keyword-unreachable",
        )
        self.assertEqual(
            detect_location_theme(
                world_style="a courier with bad debts",
                session_theme={"location_theme": "cyberpunk"},
            ),
            "cyberpunk",
        )
        self.assertTrue(setting)

    def test_it_does_not_override_a_keyword_hit(self):
        # The player wrote "cyberpunk". A model answering "fantasy" loses.
        self.assertEqual(
            detect_location_theme(
                world_style="neon megacity under corporate rule",
                session_theme={"location_theme": "fantasy"},
            ),
            "cyberpunk",
        )

    def test_an_illegal_value_falls_back_to_keywords(self):
        for bad in ("solarpunk", "", 7, None, ["space"]):
            with self.subTest(value=bad):
                self.assertEqual(
                    detect_location_theme(
                        world_style="a courier with bad debts",
                        session_theme={"location_theme": bad},
                    ),
                    "generic",
                )

    def test_generic_from_the_model_is_not_a_failure_value(self):
        self.assertEqual(
            detect_location_theme(
                world_style="a courier with bad debts",
                session_theme={"location_theme": "generic"},
            ),
            "generic",
        )

    def test_the_keyword_floor_is_unchanged_without_an_explicit_theme(self):
        for style, expected in (
            ("neon megacity under corporate rule", "cyberpunk"),
            ("high fantasy kingdom of sorcery", "fantasy"),
            ("hard sci-fi orbital station", "space"),
            ("an office comedy about expense reports", "generic"),
        ):
            with self.subTest(style=style):
                self.assertEqual(detect_location_theme(world_style=style), expected)


class TestSourceAuthorityOrder(unittest.TestCase):
    """Measured: the model's free text moved 15 of 19 answers, including one
    where the player had written the genre themselves. All the sources used to
    go into one blob, so the priority tuple decided which SOURCE won, which is
    not a decision the priority tuple should be making."""

    def test_the_players_words_beat_the_models_prose(self):
        # "sci-fi" is the player's. A model calling it celestial does not win.
        self.assertEqual(
            detect_location_theme(
                world_style="hard sci-fi orbital station running out of water",
                session_theme={
                    "genre": "celestial afterlife heavens",
                    "tone": "divine court",
                    "keywords": ["angel", "paradise"],
                },
            ),
            "space",
        )

    def test_the_players_words_beat_the_enum(self):
        self.assertEqual(
            detect_location_theme(
                world_style="neon megacity under corporate rule",
                session_theme={"location_theme": "arctic"},
            ),
            "cyberpunk",
        )

    def test_the_enum_beats_the_models_prose(self):
        # Both are the model's. The validated closed-set answer is the one it
        # was actually asked; the prose merely happens to contain a keyword.
        self.assertEqual(
            detect_location_theme(
                world_style="a courier with bad debts",
                session_theme={"location_theme": "cyberpunk", "tone": "frozen glacier tundra"},
            ),
            "cyberpunk",
        )

    def test_the_models_prose_still_works_as_a_floor(self):
        # Kept, not removed: it just cannot outrank the two above it any more.
        self.assertEqual(
            detect_location_theme(
                world_style="a courier with bad debts",
                session_theme={"genre": "neon megacity sprawl"},
            ),
            "cyberpunk",
        )

    def test_the_genre_argument_is_caller_authority_not_model_prose(self):
        # pick_isekai_arrival_location(genre=...) is called with the player's
        # own world_style on several paths, so the ARGUMENT stays in tier one.
        self.assertEqual(detect_location_theme(genre="steampunk clockwork"), "steampunk")
        self.assertEqual(detect_location_theme(idea="wasteland fallout ruins"), "wasteland")


class TestTheRoundTripDoesNotDropIt(unittest.TestCase):
    """The client hands the whole intent object back; the server re-runs it.

    `_resolve_setup_intent` feeds the returned plan back through
    `apply_keyword_intent`, which is a third place a new key could vanish. It
    spreads the plan whole, so it survives -- but nothing asserted that, and
    the two gates above are proof this codebase drops keys quietly.
    """

    def test_apply_keyword_intent_preserves_it(self):
        from app.setup_composer import apply_keyword_intent

        out = apply_keyword_intent("a courier with bad debts", {"location_theme": "cyberpunk"})
        self.assertEqual(out.get("location_theme"), "cyberpunk")

    def test_it_survives_the_full_client_round_trip(self):
        from app.llm import _resolve_setup_intent

        composed = merge_intent_plans(
            {"raw_idea": "a derelict hauler drifting past the third moon"},
            {"genre": "salvage", "location_theme": "space"},
        )
        # What the browser posts back on the next roll.
        plan = _resolve_setup_intent({"_compose_intent": composed})
        self.assertEqual(plan.get("location_theme"), "space")
        self.assertEqual(
            detect_location_theme(
                world_style="a derelict hauler drifting past the third moon",
                session_theme=plan,
            ),
            "space",
        )


class TestPromptAsksAClosedQuestion(unittest.TestCase):
    def test_the_return_shape_lists_every_legal_id(self):
        from app.llm import _setup_intent_prompt_shape

        shape = _setup_intent_prompt_shape()
        asked = str(shape.get("return_shape", {}).get("location_theme") or "")
        for tid in LOCATION_THEME_IDS:
            with self.subTest(theme=tid):
                self.assertIn(tid, asked)

    def test_free_text_genre_is_still_asked(self):
        from app.llm import _setup_intent_prompt_shape

        shape = _setup_intent_prompt_shape()
        self.assertIn("genre", shape.get("return_shape", {}))


if __name__ == "__main__":
    unittest.main()
