"""Regression tests: an unchosen start location must not carry a genre.

`start_location` defaulted to the literal "Mosswake Gate" in five separate
places -- the Advanced form shipped `value="Mosswake Gate"` in the HTML, the
submit path re-inserted it, `SETUP_STRING_DEFAULTS` held it, the Pydantic model
defaulted to it, and `start_playthrough` applied it one last time with
`options.get("start_location") or "Mosswake Gate"`.

That last one was the load-bearing bug. `ensure_isekai_start_location` already
picks a themed arrival name out of `LOCATION_SEEDS_BY_THEME` whenever the
location is empty -- including on the non-isekai path -- but the `or` filled the
empty case in *before* the picker could ever see it. So the picker existed,
worked, and was unreachable:

    space opera    Mosswake Gate   (should be e.g. Shuttle Bay Marking Paint)
    cyberpunk      Mosswake Gate   (should be e.g. Red Sector Firewall Gate)
    post-apoc      Mosswake Gate   (should be e.g. Dead Rail Switchyard)

Every world that ever left that box alone opened at a damp fantasy gate-town,
and it is the first place name a player reads. This is the same defect as the
"Riverbend Camp" leak in `tests/test_prompt_exemplar_leak.py`, arriving through
a default instead of through a prompt.

`benchmarks/run_genre_variety.py` supplies `start_location` explicitly for all
six genres, which is why the genre matrix scored "exemplar toponyms in prose:
0" while this shipped.

Run:  python -m unittest tests.test_start_location_default
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-startloc-test-"))
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
    LOCATION_SEEDS_BY_THEME,
    detect_location_theme,
    ensure_isekai_start_location,
    structural_fallback,
)
from app.world import _START_LOCATION_LAST_RESORT, norm_name  # noqa: E402

# The literal that shipped, plus the toponyms the earlier leak invented near it.
LEAKED = ("mosswake", "riverbend", "redmill")

WORLDS = {
    "space": "far-future starship lanes and colony docks",
    "cyberpunk": "neon arcology under corporate rule",
    "wasteland": "irradiated wasteland convoy survival",
    "fantasy": "high fantasy with open magic and old empires",
}


def _resolved(style: str) -> str:
    """The shipped `start_playthrough` resolution, for an untouched box."""
    loc = norm_name(str(SETUP_STRING_DEFAULTS.get("start_location") or ""))
    loc, _changed = ensure_isekai_start_location(
        loc,
        backstory_mode="",
        idea="",
        world_style=style,
        genre=style,
        character_backstory="",
        session_theme=None,
    )
    return norm_name(loc or "") or _START_LOCATION_LAST_RESORT


class TestNoGenreLiteralInTheDefault(unittest.TestCase):
    def test_setup_string_defaults_names_no_place(self):
        self.assertEqual(SETUP_STRING_DEFAULTS.get("start_location"), "")

    def test_the_advanced_form_ships_an_empty_box(self):
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8", errors="replace")
        self.assertIn('<input name="start_location" value=""', html)

    def test_no_shipped_default_carries_a_leaked_toponym(self):
        # Every layer that can put a place name in without the player asking.
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8", errors="replace")
        for line in html.splitlines():
            if 'name="start_location"' in line:
                for name in LEAKED:
                    self.assertNotIn(name, line.lower(), line.strip())

    def test_the_last_resort_is_not_a_genre_toponym(self):
        low = _START_LOCATION_LAST_RESORT.lower()
        for name in LEAKED:
            self.assertNotIn(name, low)
        self.assertTrue(_START_LOCATION_LAST_RESORT.strip())


class TestTheThemedPickerIsReachable(unittest.TestCase):
    def test_each_genre_gets_its_own_arrival_site(self):
        for theme, style in WORLDS.items():
            with self.subTest(theme=theme):
                self.assertEqual(
                    detect_location_theme(world_style=style, genre=style, idea="", session_theme=None),
                    theme,
                )

    def test_a_non_fantasy_world_never_draws_from_the_fantasy_bank(self):
        # "Mosswake Gate" is a legitimate member of the *fantasy* pool -- the bug
        # was that it also opened every space opera. So the invariant is the
        # pool a world draws from, not the name itself. Resolve repeatedly:
        # a single lucky draw proves nothing about a random picker.
        fantasy_bank = {p.lower() for p in LOCATION_SEEDS_BY_THEME["fantasy"]}
        for theme, style in WORLDS.items():
            if theme == "fantasy":
                continue
            own_bank = {p.lower() for p in LOCATION_SEEDS_BY_THEME[theme]}
            with self.subTest(theme=theme):
                for _ in range(40):
                    got = _resolved(style)
                    self.assertTrue(got.strip(), "start location resolved to nothing")
                    self.assertIn(
                        got.lower(),
                        own_bank,
                        f"{theme} world opened at {got!r}, which is not in its own bank",
                    )
                    self.assertNotIn(
                        got.lower(),
                        fantasy_bank - own_bank,
                        f"{theme} world opened at the fantasy toponym {got!r}",
                    )

    def test_a_fantasy_world_is_not_pinned_to_one_gate(self):
        # The fantasy world may legitimately land on Mosswake Gate; it must not
        # land there every time, which is what the hardcoded default did.
        seen = {_resolved(WORLDS["fantasy"]) for _ in range(40)}
        self.assertGreater(len(seen), 1, f"fantasy pinned to {seen}")

    def test_non_fantasy_worlds_do_not_all_land_on_one_name(self):
        picks = {theme: _resolved(style) for theme, style in WORLDS.items()}
        self.assertGreater(
            len(set(picks.values())),
            1,
            f"every genre resolved to the same place: {picks}",
        )

    def test_a_place_the_player_named_is_still_honoured(self):
        loc, changed = ensure_isekai_start_location(
            "Ceres Transfer Station",
            backstory_mode="",
            idea="",
            world_style=WORLDS["space"],
            genre=WORLDS["space"],
            character_backstory="",
            session_theme=None,
        )
        self.assertEqual(loc, "Ceres Transfer Station")
        self.assertFalse(changed)


class TestContaminatedValuesFallBackInGenre(unittest.TestCase):
    def test_structural_fallback_builds_a_themed_place(self):
        # Previously fell through to examples[0], a fixed "Mosswake Gate".
        for theme, style in WORLDS.items():
            own_bank = {p.lower() for p in LOCATION_SEEDS_BY_THEME[theme]}
            with self.subTest(theme=theme):
                for _ in range(20):
                    got = str(structural_fallback("start_location", {"world_style": style}) or "")
                    self.assertTrue(got.strip())
                    self.assertIn(got.lower(), own_bank, f"{theme} fell back to {got!r}")

    def test_structural_fallback_mints_a_name_rather_than_copying_one(self):
        got = str(structural_fallback("player_name", {"world_style": WORLDS["fantasy"]}) or "")
        self.assertNotIn("mara ellison", got.lower())
        self.assertNotIn("tomas reed", got.lower())


if __name__ == "__main__":
    unittest.main()
