"""Regression tests: a silent "human" must not evict the peoples the style named.

`world_races` defaults to "human" in `app/main.py`, applied whenever nobody
touches the box, and at the lint layer that is indistinguishable from a world
deliberately built with one people. So a campaign set up as

    world_style = "high fantasy with elves, dwarves and old empires"

reached `apply_consistency_lint` holding `world_races = "human"`, the race rules
were judged against it, and both rule fields were **rewritten** to human-only
boilerplate:

    before: Elves inherit glamour from the old groves; dwarves cut runes into
            stone; humans must train for years.
    after : Humans need formal training for most casting. Gifted individuals
            may hold rare innate sparks...

This is the same trap `_DEFAULTED_MAGIC_LEVELS` and `_DEFAULTED_TECH_LEVELS`
cover on their axes (see `tests/test_magic_coherence.py`), and it bites harder:
the lint does not merely misreport the world in the packet, it deletes the
elves and dwarves from the setup.

`coherent_world_races()` mirrors `coherent_magic_level()`. The recorded value is
returned untouched unless it is the silent default AND the style prose names
peoples it excludes, in which case the roster widens and the rules survive.

Only player-authored prose (`world_style`, `custom_style`) may widen the roster.
The race rule fields are the ones under audit -- letting them vote would let an
invented people promote itself into the world it was invented for.

Run:  python -m unittest tests.test_world_races_coherence
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-races-test-"))
_ENV = {
    "AI_RPG_DB": str(_TMP / "world.db"),
    "AI_RPG_PACK_DIR": str(_TMP / "packs"),
    "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
    "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
    "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
    "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
}
os.environ.update(_ENV)

from app.main import SETUP_STRING_DEFAULTS  # noqa: E402
from app.setup_composer import (  # noqa: E402
    apply_consistency_lint,
    coherent_world_races,
    is_defaulted_world_races,
    parse_world_races,
    resolve_world_races,
)

ELF_RULES = "Elves inherit glamour from the old groves; dwarves cut runes into stone; humans must train for years."
FANTASY = "high fantasy with elves, dwarves and old empires"
MUNDANE = "grounded medieval realism, no magic"


class TestTheSilentDefaultIsRecognised(unittest.TestCase):
    def test_human_is_still_the_shipped_default(self):
        # If this changes, the whole premise below needs revisiting.
        self.assertEqual(SETUP_STRING_DEFAULTS.get("world_races"), "human")

    def test_the_default_reads_as_unchosen(self):
        for value in ("human", "Human", "humans", "", None, []):
            with self.subTest(value=value):
                self.assertTrue(is_defaulted_world_races(value))

    def test_a_real_roster_does_not_read_as_unchosen(self):
        for value in ("human, elf", "dwarf", ["human", "riverfolk"]):
            with self.subTest(value=value):
                self.assertFalse(is_defaulted_world_races(value))


class TestTheStyleWidensTheRoster(unittest.TestCase):
    def test_the_recorded_high_fantasy_world(self):
        self.assertEqual(
            coherent_world_races({"world_races": "human", "world_style": FANTASY}),
            "human, elf, dwarf",
        )

    def test_humans_are_never_evicted_by_widening(self):
        got = parse_world_races(coherent_world_races({"world_races": "human", "world_style": FANTASY}))
        self.assertEqual(got[0].lower(), "human")

    def test_a_style_that_names_nobody_leaves_the_default_alone(self):
        self.assertEqual(
            coherent_world_races({"world_races": "human", "world_style": MUNDANE}),
            "human",
        )

    def test_an_explicit_roster_wins_untouched(self):
        # The player said riverfolk and not elves. The style does not overrule them.
        self.assertEqual(
            coherent_world_races({"world_races": "human, riverfolk", "world_style": FANTASY}),
            "human, riverfolk",
        )

    def test_custom_style_counts_as_player_prose(self):
        self.assertIn(
            "beastfolk",
            resolve_world_races("human", "", "The caravans are run by beastfolk clans."),
        )

    def test_race_rules_may_not_promote_their_own_inventions(self):
        # The rules are the field under audit; they get no vote on the roster.
        self.assertEqual(
            coherent_world_races(
                {
                    "world_races": "human",
                    "world_style": MUNDANE,
                    "race_magic_rules": "Elves cast freely; orcs bind blood magic.",
                }
            ),
            "human",
        )


class TestTheLintKeepsWhatTheStyleAskedFor(unittest.TestCase):
    def test_elves_and_dwarves_survive_the_lint(self):
        fields = {"race_magic_rules": ELF_RULES}
        out, dirty = apply_consistency_lint(dict(fields), context={"world_style": FANTASY, "world_races": "human"})
        self.assertEqual(out["race_magic_rules"], ELF_RULES)
        self.assertIn("world_races_widened_from_style", dirty.get("world_races") or [])
        self.assertEqual(out["world_races"], "human, elf, dwarf")

    def test_invented_peoples_are_still_stripped_when_the_style_backs_the_default(self):
        fields = {"race_magic_rules": "Elves cast freely; dwarves use runes; orcs bind blood magic."}
        out, _dirty = apply_consistency_lint(dict(fields), context={"world_style": MUNDANE, "world_races": "human"})
        self.assertNotEqual(out["race_magic_rules"], fields["race_magic_rules"])
        self.assertNotIn("elves", out["race_magic_rules"].lower())

    def test_an_explicit_roster_still_governs_the_rules(self):
        fields = {"race_magic_rules": "Elves cast freely; dwarves use runes."}
        out, _dirty = apply_consistency_lint(
            dict(fields), context={"world_style": FANTASY, "world_races": "human, riverfolk"}
        )
        self.assertNotEqual(out["race_magic_rules"], fields["race_magic_rules"])


if __name__ == "__main__":
    unittest.main()
