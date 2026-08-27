"""Judge the theme keyword table against a committed corpus of settings.

The table has been hand-edited repeatedly and twice a change had to be reverted
because it re-themed a setting nobody was checking. The sweep that caught both
was never committed, so every later edit was made without a gate. This is the
gate.

Failure output names the setting, the expectation and the actual result,
because a bare count tells you nothing about which keyword you just broke.

`known_failing` entries are asserted to STILL FAIL. That is deliberate: it lets
the corpus record what the right answer is without being authored around the
current bug, and it means fixing one is a visible, single-line change to this
fixture in the same commit as the code fix.

Run:  python -m unittest tests.test_setting_corpus
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-settingcorpus-test-"))
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
    LOCATION_THEME_KEYWORDS,
    LOCATION_THEME_PRIORITY,
    detect_location_theme,
)

CORPUS_PATH = ROOT / "tests" / "fixtures" / "setting_corpus.json"
CORPUS: list[dict] = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))["settings"]


def _resolve(entry: dict) -> str:
    return detect_location_theme(world_style=str(entry["setting"]))


class TestCorpusShape(unittest.TestCase):
    def test_corpus_is_big_enough_to_be_a_gate(self):
        self.assertGreaterEqual(len(CORPUS), 60, "the corpus is the deliverable; keep it wide")

    def test_every_expectation_names_a_real_theme(self):
        legal = set(LOCATION_SEEDS_BY_THEME) | {"generic"}
        for entry in CORPUS:
            with self.subTest(setting=entry["setting"]):
                self.assertIn(entry["expected"], legal)
                for allowed in entry.get("allowed") or []:
                    self.assertIn(allowed, legal)

    def test_settings_are_unique(self):
        seen = [e["setting"] for e in CORPUS]
        self.assertEqual(len(seen), len(set(seen)))

    def test_known_failing_entries_carry_a_reason(self):
        for entry in CORPUS:
            if entry.get("known_failing"):
                with self.subTest(setting=entry["setting"]):
                    self.assertTrue(
                        str(entry.get("note") or "").strip(),
                        "a known_failing entry must say what is wrong",
                    )


class TestPriorityCoversTheTable(unittest.TestCase):
    """A theme in one and not the other is a silent no-op, not an error."""

    def test_every_keyword_theme_is_tested(self):
        forgotten = [t for t in LOCATION_THEME_KEYWORDS if t not in LOCATION_THEME_PRIORITY]
        self.assertEqual(
            forgotten, [], f"themes with keywords that are never tested: {forgotten}"
        )

    def test_every_tested_theme_has_keywords(self):
        empty = [t for t in LOCATION_THEME_PRIORITY if not LOCATION_THEME_KEYWORDS.get(t)]
        self.assertEqual(empty, [], f"themes tested with no keywords: {empty}")

    def test_every_reachable_theme_has_a_bank(self):
        # A theme detect_location_theme can return with nowhere to draw names
        # from falls through to the fantasy bank -- the exact default that used
        # to open superhero and heist games at a gate-town.
        bankless = [t for t in LOCATION_THEME_PRIORITY if not LOCATION_SEEDS_BY_THEME.get(t)]
        self.assertEqual(bankless, [], f"reachable themes with no bank: {bankless}")

    def test_fantasy_is_tested_last(self):
        self.assertEqual(LOCATION_THEME_PRIORITY[-1], "fantasy")


class TestUnambiguousSettings(unittest.TestCase):
    def test_each_resolves_to_its_expected_theme(self):
        misses = []
        for entry in CORPUS:
            if entry.get("allowed") or entry.get("known_failing"):
                continue
            actual = _resolve(entry)
            if actual != entry["expected"]:
                misses.append(f"  {entry['setting']!r}\n    expected {entry['expected']}, got {actual}")
        self.assertEqual(misses, [], "\n" + "\n".join(misses))


class TestAmbiguousSettings(unittest.TestCase):
    def test_each_lands_somewhere_defensible(self):
        misses = []
        for entry in CORPUS:
            allowed = entry.get("allowed")
            if not allowed or entry.get("known_failing"):
                continue
            actual = _resolve(entry)
            if actual not in allowed:
                misses.append(f"  {entry['setting']!r}\n    allowed {allowed}, got {actual}")
        self.assertEqual(misses, [], "\n" + "\n".join(misses))


class TestKnownFailuresHaveNotBeenFixedQuietly(unittest.TestCase):
    """If one of these starts passing, take the flag off in the same commit."""

    def test_still_failing(self):
        fixed = []
        for entry in CORPUS:
            if not entry.get("known_failing"):
                continue
            actual = _resolve(entry)
            if actual == entry["expected"]:
                fixed.append(
                    f"  {entry['setting']!r} now resolves to {actual}; "
                    f"drop known_failing from the fixture"
                )
        self.assertEqual(fixed, [], "\n" + "\n".join(fixed))


if __name__ == "__main__":
    unittest.main()
