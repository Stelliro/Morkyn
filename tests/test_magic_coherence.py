"""Regression tests: do not tell the open-magic world that magic is rare.

`magic_level` defaults to "rare" in `app/main.py`, applied whenever nobody
touches the dropdown, and at the packet layer that is indistinguishable from a
deliberate pick. So a campaign set up as

    world_style = "high fantasy with open magic and old empires"

shipped `"magic_level": "rare"` beside that line on every single turn. The prose
obeyed the state rather than the style, and high fantasy came out the weakest of
six settings in the genre matrix -- 1 of 8 on its own genre vocabulary, with a
hedge-mage protagonist and a spirit debt in the backstory.

This is the same trap `_DEFAULTED_TECH_LEVELS` already covers on the technology
axis, where an unset dropdown told a far-future starship world it was iron age.
`coherent_magic_level()` mirrors `coherent_tech_level()` exactly: the recorded
value is returned untouched unless it is the silent default AND the style prose
describes a different world.

Run:  python -m unittest tests.test_magic_coherence
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-magic-test-"))
_ENV = {
    "AI_RPG_DB": str(_TMP / "world.db"),
    "AI_RPG_PACK_DIR": str(_TMP / "packs"),
    "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
    "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
    "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
    "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
}
os.environ.update(_ENV)

from app.setup_composer import MAGIC_LEVEL_VALUES  # noqa: E402
from app.world import coherent_magic_level, resolve_world_magic  # noqa: E402


class TestTheSilentRareDefault(unittest.TestCase):
    def test_the_recorded_high_fantasy_world(self):
        # The exact setup from benchmarks/run_genre_variety.py.
        self.assertEqual(
            coherent_magic_level(
                {
                    "magic_level": "rare",
                    "world_style": "high fantasy with open magic and old empires",
                }
            ),
            "common utility",
        )

    def test_prose_that_rules_magic_out(self):
        self.assertEqual(
            coherent_magic_level(
                {"magic_level": "rare", "world_style": "grounded medieval realism, no magic"}
            ),
            "none",
        )

    def test_prose_that_asks_for_cultivation(self):
        self.assertEqual(
            coherent_magic_level(
                {"magic_level": "rare", "world_style": "wuxia sect politics and cultivation"}
            ),
            "cultivation",
        )

    def test_prose_that_outlaws_magic(self):
        self.assertEqual(
            coherent_magic_level({"magic_level": "rare", "world_style": "post-magic wasteland"}),
            "forbidden",
        )

    def test_the_default_survives_when_nothing_contradicts_it(self):
        for style in (
            "low fantasy mud and knives",
            "frontier dark fantasy",
            "near-future cyberpunk megacity",
            "",
        ):
            with self.subTest(style=style):
                self.assertEqual(
                    coherent_magic_level({"magic_level": "rare", "world_style": style}), "rare"
                )

    def test_an_explicit_pick_is_never_overridden(self):
        # Someone who deliberately chose "none" gets none, whatever the style
        # says. Only the silent default yields.
        self.assertEqual(
            coherent_magic_level(
                {"magic_level": "none", "world_style": "high fantasy with open magic"}
            ),
            "none",
        )
        self.assertEqual(
            coherent_magic_level(
                {"magic_level": "cultivation", "world_style": "no magic anywhere"}
            ),
            "cultivation",
        )

    def test_an_empty_setup_still_answers(self):
        self.assertEqual(coherent_magic_level({}), "rare")
        self.assertEqual(coherent_magic_level(None), "rare")


class TestTheAnswerIsAlwaysCanonical(unittest.TestCase):
    def test_every_resolution_is_a_real_option(self):
        styles = [
            "high fantasy with open magic and old empires",
            "grounded medieval realism, no magic",
            "wuxia sect politics and cultivation",
            "post-magic wasteland",
            "far-future interstellar civilisation",
            "1880s frontier west with quiet, unexplained wrongness",
            "mage academy intrigue with spell markets",
            "",
        ]
        for style in styles:
            with self.subTest(style=style):
                value = coherent_magic_level({"magic_level": "rare", "world_style": style})
                self.assertIn(value, MAGIC_LEVEL_VALUES, f"{value!r} is not a UI option")


class TestPrecedenceBetweenHints(unittest.TestCase):
    """Order matters: several of these blurbs match more than one bucket."""

    def test_no_magic_beats_the_bare_word_magic(self):
        self.assertEqual(resolve_world_magic("", "a world with no magic at all"), "none")

    def test_cultivation_beats_generic_open_magic(self):
        # A xianxia blurb mentions open magic too; the ladder is more specific.
        self.assertEqual(
            resolve_world_magic("", "cultivation sects where open magic is everywhere"),
            "cultivation",
        )

    def test_forbidden_beats_common(self):
        self.assertEqual(
            resolve_world_magic("", "magic is banned, though every city has mage academies"),
            "forbidden",
        )

    def test_custom_style_is_read_too(self):
        self.assertEqual(
            coherent_magic_level({"magic_level": "rare", "custom_style": "open magic, guild-run"}),
            "common utility",
        )


if __name__ == "__main__":
    unittest.main()
