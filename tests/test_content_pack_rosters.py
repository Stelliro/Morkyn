"""The content-pack rosters, and how hard each one is enforced.

Audited 2026-08-27 while sweeping for the mint-on-miss defect that bit skills
(`resolve_check` inventing a phantom) and equipment slots (`_slot_by_ref`
ignoring its own `accepts` list). These four are **not** that bug. They sit in
`validate_pack`, which rejects or warns rather than inventing, and `STAT_KEYS`
is the one place in the codebase that already did the right thing: a roster
plus an alias table the lookup actually consults.

What the sweep did find is written down here so the docstrings on those
constants cannot quietly go stale:

  ACTIVATIONS / RESOURCE_KEYS  hard error on an unknown value
  STAT_KEYS                    hard error, with aliases normalized first
  SKILL_CATEGORIES             WARNING only, and the value is stored as written
  SECTIONS                     referenced nowhere; enforcing nothing

The category one is the one with teeth, and they are hidden: `search_skills`
and `gm_context_block` both filter on `enabled_categories`, which defaults to
exactly the eight known categories. A pack that mistypes a category installs
fine, warns once, and its skill is then invisible to both.

Run:  python -m unittest tests.test_content_pack_rosters
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-packroster-test-"))
os.environ.update({
    "AI_RPG_DB": str(_TMP / "world.db"),
    "AI_RPG_PACK_DIR": str(_TMP / "packs"),
    "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
    "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
    "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
    "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
})

from app.content_packs import (  # noqa: E402
    ACTIVATIONS,
    RESOURCE_KEYS,
    SKILL_CATEGORIES,
    STAT_KEYS,
    normalize_stat_key,
    validate_pack,
)
from app.skill_checks import CATEGORIES  # noqa: E402


def _pack(**sections):
    base = {"format": "morkyn-content-pack-v1", "id": "probe", "name": "Probe", "version": "1"}
    base.update(sections)
    return validate_pack(base)


def _paths(items):
    return {str(i.get("path") or "") for i in items or []}


class TestHardRosters(unittest.TestCase):
    """An unknown value must fail validation, not install quietly."""

    def test_an_unknown_activation_is_an_error(self):
        res = _pack(powers=[{"code": "p", "name": "P", "activation": "channelled"}])
        self.assertIn("powers[0].activation", _paths(res["errors"]))

    def test_every_known_activation_is_accepted(self):
        for act in ACTIVATIONS:
            with self.subTest(activation=act):
                res = _pack(powers=[{"code": "p", "name": "P", "activation": act}])
                self.assertNotIn("powers[0].activation", _paths(res["errors"]))

    def test_an_unknown_resource_is_an_error(self):
        res = _pack(powers=[{"code": "p", "name": "P", "activation": "active",
                             "resource_cost": {"stamina": 2, "grit": 1}}])
        paths = _paths(res["errors"])
        self.assertIn("powers[0].resource_cost.stamina", paths)
        self.assertIn("powers[0].resource_cost.grit", paths)

    def test_every_known_resource_is_accepted(self):
        for res_key in RESOURCE_KEYS:
            with self.subTest(resource=res_key):
                res = _pack(powers=[{"code": "p", "name": "P", "activation": "active",
                                     "resource_cost": {res_key: 1}}])
                self.assertFalse([p for p in _paths(res["errors"]) if "resource_cost" in p])

    def test_an_unknown_attribute_is_an_error(self):
        res = _pack(skills=[{"code": "s", "name": "S", "attribute": "vigor"}])
        self.assertIn("skills[0].attribute", _paths(res["errors"]))

    def test_stat_aliases_are_normalized_rather_than_rejected(self):
        # The pattern the rest of the codebase should have copied: a roster
        # whose synonym table the lookup actually consults.
        for alias, canon in (("might", "strength"), ("agility", "dexterity"),
                             ("stamina", "constitution"), ("awareness", "wisdom")):
            with self.subTest(alias=alias):
                self.assertEqual(normalize_stat_key(alias), canon)
        for key in STAT_KEYS:
            self.assertEqual(normalize_stat_key(key), key)


class TestSkillCategoryIsSoft(unittest.TestCase):
    """Documented as a warning. If that ever hardens, the docstring is wrong."""

    def test_an_unknown_category_warns_and_does_not_error(self):
        res = _pack(skills=[{"code": "s", "name": "S", "attribute": "dexterity",
                             "category": "NOT_A_CATEGORY"}])
        self.assertNotIn("skills[0].category", _paths(res["errors"]))
        self.assertIn("skills[0].category", _paths(res["warnings"]))

    def test_the_off_roster_category_is_stored_as_written(self):
        res = _pack(skills=[{"code": "s", "name": "S", "attribute": "dexterity",
                             "category": "NOT_A_CATEGORY"}])
        stored = (res.get("pack") or {}).get("skills") or [{}]
        self.assertEqual(stored[0].get("category"), "not_a_category")

    def test_such_a_skill_is_invisible_to_the_default_category_filter(self):
        # This is the silent consequence: default enabled_categories is exactly
        # the eight known ones, and search_skills / gm_context_block both drop
        # anything outside it.
        from app.skill_checks import default_check_settings

        enabled = set(default_check_settings().get("enabled_categories") or [])
        self.assertEqual(enabled, set(SKILL_CATEGORIES))
        self.assertNotIn("not_a_category", enabled)


class TestTheTwoCategoryRostersDoNotDrift(unittest.TestCase):
    def test_content_packs_and_skill_checks_agree(self):
        # These are separate definitions in separate modules. The attribute
        # alias tables drifted exactly this way before being merged.
        self.assertEqual(sorted({c["id"] for c in CATEGORIES}), sorted(SKILL_CATEGORIES))


class TestSectionsIsNotEnforcing(unittest.TestCase):
    def test_sections_has_no_consumer(self):
        # Documented as unused. If someone wires it up, this test should be the
        # thing that tells them to fix the docstring too.
        hits = 0
        for path in (ROOT / "app").glob("*.py"):
            text = path.read_text(encoding="utf-8", errors="replace")
            hits += sum(
                1
                for line in text.splitlines()
                if "SECTIONS" in line and not line.strip().startswith(("#", '"""', "SECTIONS ="))
            )
        self.assertEqual(hits, 0, "SECTIONS now has a consumer; update its docstring")


if __name__ == "__main__":
    unittest.main()
