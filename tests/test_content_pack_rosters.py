"""The content-pack rosters, and how hard each one is enforced.

Audited 2026-08-27 while sweeping for the mint-on-miss defect that bit skills
(`resolve_check` inventing a phantom) and equipment slots (`_slot_by_ref`
ignoring its own `accepts` list). These four are **not** that bug. They sit in
`validate_pack`, which rejects or warns rather than inventing, and `STAT_KEYS`
is the one place in the codebase that already did the right thing: a roster
plus an alias table the lookup actually consults.

What the sweep found, and what was then done about it:

  ACTIVATIONS       hard error on an unknown value. Unchanged.
  STAT_KEYS         hard error, aliases normalized first. The correct pattern.
  RESOURCE_KEYS     was a hard error with NO alias table, so "stamina" and "hp"
                    were refused while "str" and "might" mapped happily. Now
                    normalized through RESOURCE_ALIASES first; a genuinely
                    unknown resource is still a hard error.
  SKILL_CATEGORIES  still warning-only, but no longer stored as written. It
                    used to install the off-roster value and then let
                    `search_skills` and `gm_context_block` filter the skill out
                    of existence -- both filter on `enabled_categories`, which
                    defaults to exactly the eight known ones. A typo cost the
                    author the whole skill, silently. Now mapped through
                    SKILL_CATEGORY_ALIASES and falling back to "general".
  SECTIONS          referenced nowhere, enforcing nothing. Now wired: an
                    unknown top-level key warns. `_as_list(payload.get(...))`
                    returns [] for a missing key, so "skils" used to install
                    cleanly with zero skills and no explanation.

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
    normalize_resource_key,
    normalize_skill_category,
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

    def test_an_unknown_resource_is_still_an_error(self):
        res = _pack(powers=[{"code": "p", "name": "P", "activation": "active",
                             "resource_cost": {"grit": 1, "willpower": 2}}])
        paths = _paths(res["errors"])
        self.assertIn("powers[0].resource_cost.grit", paths)
        self.assertIn("powers[0].resource_cost.willpower", paths)

    def test_resource_aliases_are_normalized_rather_than_rejected(self):
        # "str" mapped to strength while "hp" was a hard error. No reason.
        for alias, canon in (("stamina", "energy"), ("hp", "health"),
                             ("mp", "mana"), ("coin", "gold"), ("focus", "mana")):
            with self.subTest(alias=alias):
                self.assertEqual(normalize_resource_key(alias), canon)
                res = _pack(powers=[{"code": "p", "name": "P", "activation": "active",
                                     "resource_cost": {alias: 3}}])
                self.assertFalse([p for p in _paths(res["errors"]) if "resource_cost" in p])
                cost = ((res.get("pack") or {}).get("powers") or [{}])[0].get("resource_cost") or {}
                self.assertEqual(cost.get(canon), 3, f"{alias} should be stored as {canon}")

    def test_an_alias_never_invents_a_resource(self):
        # Aliases may only point at resources the engine already models.
        from app.content_packs import RESOURCE_ALIASES

        for alias, canon in RESOURCE_ALIASES.items():
            with self.subTest(alias=alias):
                self.assertIn(canon, RESOURCE_KEYS)
                self.assertNotIn(alias, RESOURCE_KEYS, "an alias must not shadow a real key")

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


class TestSkillCategoryIsSoftButNoLongerSilent(unittest.TestCase):
    """A typo should not stop a pack installing. It should not delete the skill
    from the game either, which is what storing it as written amounted to."""

    def test_an_unknown_category_warns_and_does_not_error(self):
        res = _pack(skills=[{"code": "s", "name": "S", "attribute": "dexterity",
                             "category": "NOT_A_CATEGORY"}])
        self.assertNotIn("skills[0].category", _paths(res["errors"]))
        self.assertIn("skills[0].category", _paths(res["warnings"]))

    def test_the_warning_says_what_was_actually_stored(self):
        res = _pack(skills=[{"code": "s", "name": "S", "attribute": "dexterity",
                             "category": "NOT_A_CATEGORY"}])
        warning = [w for w in res["warnings"] if w.get("path") == "skills[0].category"][0]
        self.assertIn("general", warning.get("message", ""))

    def test_an_off_roster_category_never_reaches_the_database(self):
        res = _pack(skills=[{"code": "s", "name": "S", "attribute": "dexterity",
                             "category": "NOT_A_CATEGORY"}])
        stored = (res.get("pack") or {}).get("skills") or [{}]
        self.assertEqual(stored[0].get("category"), "general")

    def test_category_aliases_keep_the_authors_meaning(self):
        for alias, canon in (("crafting", "craft"), ("fighting", "combat"),
                             ("knowledge", "mental"), ("body", "physical"),
                             ("misc", "general")):
            with self.subTest(alias=alias):
                self.assertEqual(normalize_skill_category(alias), (canon, True))

    def test_every_stored_category_is_visible_to_the_default_filter(self):
        # The silent consequence that made this worth fixing: default
        # enabled_categories is exactly the eight known ones, and search_skills
        # / gm_context_block both drop anything outside it. Since a stored
        # category can no longer be off-roster, a pack skill cannot vanish.
        from app.skill_checks import default_check_settings

        enabled = set(default_check_settings().get("enabled_categories") or [])
        self.assertEqual(enabled, set(SKILL_CATEGORIES))
        for probe in ("NOT_A_CATEGORY", "stealthy", "", None, "crafting", 5):
            with self.subTest(category=probe):
                stored, _ = normalize_skill_category(probe)
                self.assertIn(stored, enabled, f"{probe!r} stored as {stored!r}, which is filtered out")


class TestTheTwoCategoryRostersDoNotDrift(unittest.TestCase):
    def test_content_packs_and_skill_checks_agree(self):
        # These are separate definitions in separate modules. The attribute
        # alias tables drifted exactly this way before being merged.
        self.assertEqual(sorted({c["id"] for c in CATEGORIES}), sorted(SKILL_CATEGORIES))


class TestSectionsIsWiredUp(unittest.TestCase):
    """It was referenced nowhere. A mistyped section is silent without it:
    `_as_list(payload.get("skills"))` returns [] for a missing key, so "skils"
    installs cleanly, reports zero skills, and explains nothing."""

    def test_a_mistyped_section_is_reported(self):
        res = _pack(skils=[{"code": "s", "name": "S", "attribute": "dexterity"}])
        self.assertIn("skils", _paths(res["warnings"]))
        self.assertEqual((res.get("pack") or {}).get("skills"), [])

    def test_the_warning_suggests_the_section_meant(self):
        res = _pack(skils=[{"code": "s", "name": "S"}])
        warning = [w for w in res["warnings"] if w.get("path") == "skils"][0]
        self.assertIn("skills", warning.get("fix", ""))

    def test_a_real_section_is_not_reported(self):
        res = _pack(skills=[{"code": "s", "name": "S", "attribute": "dexterity"}])
        self.assertNotIn("skills", _paths(res["warnings"]))

    def test_metadata_keys_are_not_reported(self):
        res = validate_pack({
            "format": "morkyn-content-pack-v1", "id": "probe", "name": "Probe",
            "label": "Probe", "version": "2", "author": "someone",
            "description": "a pack", "_note": "private",
            "skills": [{"code": "s", "name": "S", "attribute": "dexterity"}],
        })
        unexpected = _paths(res["warnings"]) & {
            "format", "id", "name", "label", "version", "author", "description", "_note",
        }
        self.assertEqual(unexpected, set())

    def test_it_is_a_warning_and_never_blocks_the_install(self):
        res = _pack(skils=[], something_else={"a": 1},
                    skills=[{"code": "s", "name": "S", "attribute": "dexterity"}])
        self.assertTrue(res["ok"], "an unknown key must not stop a pack installing")


if __name__ == "__main__":
    unittest.main()
