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


class TestMagicLevelReachesTheSeedPool(unittest.TestCase):
    """The setting must change which abilities the offline generator can mint.

    `pick_seed_skill_domain` had no `magic_level` parameter at all, so the four
    supernatural lanes (arcane / summon / necro / hybrid, 66 of the 189 seeds)
    were on the table in every world. Measured over 400 offline rolls per setup,
    a world with magic switched off produced at least one supernatural ability
    66% of the time and a cultivation world 69% -- the dropdown was inert.
    """

    RUNS = 300

    def _lane_of(self, name):
        from app.setup_composer import SEED_SKILL_DOMAIN_POOL

        for d in SEED_SKILL_DOMAIN_POOL:
            if str(d.get("name")) == str(name):
                return str(d.get("lane") or "")
        return ""

    def _supernatural_rate(self, setup):
        from app.llm import _fallback_special_abilities
        from app.setup_composer import SUPERNATURAL_LANES

        hits = 0
        for _ in range(self.RUNS):
            out = _fallback_special_abilities(dict(setup))
            if any(self._lane_of(a.get("name")) in SUPERNATURAL_LANES for a in out):
                hits += 1
        return hits / self.RUNS

    def test_the_parameter_exists_at_all(self):
        import inspect

        from app.setup_composer import pick_seed_skill_domain

        params = inspect.signature(pick_seed_skill_domain).parameters
        self.assertIn("magic_level", params)
        self.assertIn("race_magic_enabled", params)

    def test_a_no_magic_world_mints_no_supernatural_seeds(self):
        from app.setup_composer import SUPERNATURAL_LANES, pick_seed_skill_domain

        for i in range(600):
            dom = pick_seed_skill_domain(
                world_style="high magic academy",  # style pulls toward arcane; magic_level must win
                magic_level="none",
                race_magic_enabled=False,
                salt=f"nomagic|{i}",
            )
            self.assertNotIn(
                str(dom.get("lane") or ""),
                SUPERNATURAL_LANES,
                f"{dom.get('name')} ({dom.get('lane')}) rolled in a world with magic off",
            )

    def test_racial_magic_reopens_the_lanes_when_ambient_magic_is_none(self):
        from app.setup_composer import SUPERNATURAL_LANES, pick_seed_skill_domain

        seen = {
            str(
                pick_seed_skill_domain(
                    magic_level="none", race_magic_enabled=True, salt=f"racial|{i}"
                ).get("lane")
                or ""
            )
            for i in range(400)
        }
        self.assertTrue(seen & SUPERNATURAL_LANES, "race_magic_enabled must reopen the magic lanes")

    def _lane_rate(self, *, style, magic_level, n=6000):
        """Share of picks landing in a supernatural lane. Cheap enough to sample hard."""
        from app.setup_composer import SUPERNATURAL_LANES, pick_seed_skill_domain

        hits = sum(
            1
            for i in range(n)
            if str(
                pick_seed_skill_domain(
                    world_style=style, magic_level=magic_level, salt=f"{magic_level}|{style}|{i}"
                ).get("lane")
                or ""
            )
            in SUPERNATURAL_LANES
        )
        return hits / n

    def test_the_off_lane_die_carries_no_supernatural_face(self):
        """Second layer behind the pool filter: the die must not offer magic lanes."""
        from app.setup_composer import MAGIC_LANE_DIE, SUPERNATURAL_LANES

        self.assertTrue(set(MAGIC_LANE_DIE["off"]).isdisjoint(SUPERNATURAL_LANES))
        self.assertTrue(set(MAGIC_LANE_DIE["rare"]) & SUPERNATURAL_LANES)
        self.assertGreater(
            MAGIC_LANE_DIE["common"].count("arcane"),
            MAGIC_LANE_DIE["rare"].count("arcane"),
            "a high-magic world must weight the arcane lane above a rare one",
        )

    def test_a_high_magic_world_rolls_magic_lanes_far_more_often(self):
        # Measured: rare 0.397, cultivation 0.542 over 6000 picks. Removing the
        # high-magic lane-roll boost drops cultivation to 0.487, so 0.52 separates
        # them at roughly five standard deviations.
        rare = self._lane_rate(style="Survival Fantasy", magic_level="rare")
        high = self._lane_rate(style="Survival Fantasy", magic_level="cultivation")
        self.assertGreater(rare, 0.30, f"rare magic still exists (got {rare:.3f})")
        self.assertLess(rare, 0.50, f"rare magic is not high magic (got {rare:.3f})")
        self.assertGreater(high, 0.52, f"high magic must clear 0.52 (got {high:.3f})")
        self.assertGreater(high - rare, 0.10, f"gap too small: {high:.3f} vs {rare:.3f}")

    def test_a_grounded_style_cannot_mute_a_high_magic_world(self):
        """"grim industrial city" steers to mundane/support/tool; magic must survive it."""
        rate = self._lane_rate(style="grim industrial city", magic_level="cultivation")
        self.assertGreater(rate, 0.35, f"style branch suppressed high magic (got {rate:.3f})")

    def test_the_offline_generator_obeys_the_setting(self):
        off = self._supernatural_rate(
            {"magic_level": "none", "race_magic_enabled": False, "world_style": "Survival Fantasy"}
        )
        rare = self._supernatural_rate(
            {"magic_level": "rare", "race_magic_enabled": True, "world_style": "Survival Fantasy"}
        )
        high = self._supernatural_rate(
            {"magic_level": "cultivation", "race_magic_enabled": True, "world_style": "Survival Fantasy"}
        )
        self.assertEqual(off, 0.0, "magic off must never mint a supernatural ability")
        self.assertGreater(rare, 0.4, f"magic on should still mint magic (got {rare:.0%})")
        self.assertGreater(
            high, rare, f"a high-magic world should out-mint a rare one ({high:.0%} vs {rare:.0%})"
        )

    def test_the_supernatural_randomizer_fallbacks_are_lane_tagged(self):
        """The filter can only exclude what carries a lane. These five are magic."""
        from app.llm import SETUP_RANDOMIZER_ABILITY_FALLBACKS
        from app.setup_composer import SUPERNATURAL_LANES

        by_name = {str(a.get("name")): a for a in SETUP_RANDOMIZER_ABILITY_FALLBACKS}
        for name in ("Residue Glow", "Ward Itch", "Echo Step", "Ashen Oath", "Rust Touch"):
            self.assertIn(name, by_name)
            self.assertIn(
                str(by_name[name].get("lane") or ""),
                SUPERNATURAL_LANES,
                f"{name} is supernatural but carries no lane, so no filter can see it",
            )

    def test_the_curated_randomizer_pool_is_currently_unreachable(self):
        """Documents a separate defect rather than pretending the filter is exercised.

        `_fallback_special_abilities` inserts `min(4, count + 1)` seed-domain
        entries at the head of `ordered` and then reads `ordered[i]` for
        `i < count`, while `_roll_ability_count` caps count at 4. The seeds
        therefore shadow all 14 curated entries every time. Measured: 0 of ~1000
        generated abilities came from SETUP_RANDOMIZER_ABILITY_FALLBACKS.

        When that shadowing is fixed, this test should start failing — at which
        point the lane filter above becomes load-bearing and the end-to-end
        assertion (no supernatural names with magic off) should replace it.
        """
        from app.llm import SETUP_RANDOMIZER_ABILITY_FALLBACKS, _fallback_special_abilities

        curated = {str(a.get("name")) for a in SETUP_RANDOMIZER_ABILITY_FALLBACKS}
        seen = set()
        for _ in range(self.RUNS):
            for ability in _fallback_special_abilities(
                {"magic_level": "rare", "race_magic_enabled": True, "world_style": "Survival Fantasy"}
            ):
                seen.add(str(ability.get("name")))
        self.assertEqual(
            seen & curated,
            set(),
            "the curated pool became reachable — swap this test for the end-to-end filter check",
        )


class TestAbilityCostsHonourMagic(unittest.TestCase):
    """`diversify_ability_costs` read a `_magic_level` key nothing ever writes.

    `magic_allows_mana("")` is False, so the computed value was False in every
    world; the call compensated by passing a hardcoded True, which left mana
    costs on abilities in worlds where magic is switched off.
    """

    def test_the_phantom_key_is_no_longer_read(self):
        """Nothing writes `_magic_level`, so reading it back can only mislead."""
        import inspect

        from app.llm import diversify_ability_costs

        src = inspect.getsource(diversify_ability_costs)
        self.assertNotIn('get("_magic_level")', src)
        self.assertIn("magic_ok", inspect.signature(diversify_ability_costs).parameters)

    def test_magic_off_strips_mana_from_costs(self):
        from app.llm import diversify_ability_costs

        abilities = [
            {"name": "A", "description": "x", "resource_cost": {"mana": 3}, "power_type": "linear"},
            {"name": "B", "description": "y", "resource_cost": {"mana": 5}, "power_type": "linear"},
        ]
        out = diversify_ability_costs(abilities, force=True, magic_ok=False)
        for ability in out:
            self.assertEqual(
                int((ability.get("resource_cost") or {}).get("mana") or 0),
                0,
                f"{ability.get('name')} kept a mana cost in a world with no magic",
            )

    def test_a_mana_cost_is_never_charged_against_a_zero_mana_pool(self):
        """`magic_allows_mana` also decides `max_mana`, so the two must agree.

        A world it answers False for grants max_mana 0; an ability costing mana
        there would simply be uncastable.
        """
        from app.llm import diversify_ability_costs
        from app.player_resources import default_resource_caps, magic_allows_mana

        for options in (
            {"magic_level": "none"},
            {"magic_level": "none", "game_system": True},
            {"magic_level": "rare"},
            {"magic_level": "cultivation"},
            {},
        ):
            allows = magic_allows_mana(str(options.get("magic_level") or ""), options)
            caps = default_resource_caps(options)
            if not allows:
                self.assertEqual(caps["max_mana"], 0, f"{options} grants mana it disallows")
            out = diversify_ability_costs(
                [
                    {"name": "A", "description": "x", "resource_cost": {"mana": 4}, "power_type": "linear"},
                    {"name": "B", "description": "y", "resource_cost": {"mana": 2}, "power_type": "linear"},
                ],
                force=True,
                magic_ok=allows,
            )
            for ability in out:
                mana = int((ability.get("resource_cost") or {}).get("mana") or 0)
                self.assertLessEqual(
                    mana,
                    caps["max_mana"],
                    f"{options}: {ability.get('name')} costs {mana} mana against a "
                    f"{caps['max_mana']} pool",
                )

    def test_magic_on_keeps_mana_available(self):
        from app.llm import diversify_ability_costs

        abilities = [
            {"name": "A", "description": "x", "resource_cost": {"mana": 3}, "power_type": "linear"},
            {"name": "B", "description": "y", "resource_cost": {"mana": 5}, "power_type": "linear"},
        ]
        out = diversify_ability_costs(abilities, force=True, magic_ok=True)
        self.assertTrue(
            any(int((a.get("resource_cost") or {}).get("mana") or 0) > 0 for a in out),
            "magic on must leave at least one mana cost standing",
        )


if __name__ == "__main__":
    unittest.main()
