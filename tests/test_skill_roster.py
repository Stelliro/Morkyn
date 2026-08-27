"""Regression tests: model-supplied skill text must meet the roster before minting.

The skill system had no tests at all -- only two `tools/` probes, neither of
which asserts anything about a skill's name, description, or attribute.

`resolve_check` looked its skill up by exact code:

    skill = library.get(skill_code) or library.get(_codeify(skill_code))
    if not skill:
        reg = register_or_adjust_skill({"name": skill_code, "source": "playthrough"})

The narrator supplies that string as free text (`app/world.py` feeds
`item.get("skill")` straight in) and is never shown the 60 built-in skills --
only the player's own 12 reach the packet. So "pick the lock" missed
`lockpicking`, which was sitting in the library with `tags` naming it, and the
game minted a phantom instead. Three things went wrong at once:

    code='pick_lock'
      NAME       : 'pick_lock'                 <- raw string, rendered in the UI
      DESCRIPTION: 'Related to General Check: Fallback when no specialized
                    skill fits.'               <- grafted from an unrelated skill
      attribute  : 'intelligence'              <- so lockpicking rolled INT

The description graft fired because `skill_similarity` scored `category` and
`attribute` -- fields `_skill_row` had defaulted to "general"/"intelligence" a
few lines earlier. That is 0.45 against a 0.35 threshold from the defaults
alone, so every minted skill matched a general-category skill and inherited its
description. Every improvised skill in a campaign ended up described as a
fallback check.

The attribute was the one that changed outcomes, silently: a lockpicking roll
looks normal in the UI whether it used DEX or INT.

`resolve_skill_code` now walks code -> codeified -> name -> unambiguous tag ->
the existing regex trigger table, and returns None rather than guessing.
Matching is whole-word only: the `picking`/`king` and `sector`/`sect` bugs came
from substring shortcuts and must not come back here.

Run:  python -m unittest tests.test_skill_roster
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-skillroster-test-"))
_ENV = {
    "AI_RPG_DB": str(_TMP / "world.db"),
    "AI_RPG_PACK_DIR": str(_TMP / "packs"),
    "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
    "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
    "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
    "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
}
os.environ.update(_ENV)

from app.skill_checks import (  # noqa: E402
    BUILTIN_SKILLS,
    SKILL_TRIGGER_PATTERNS,
    infer_check_from_action,
    register_or_adjust_skill,
    resolve_skill_code,
)

BUILT = {s["code"]: s for s in BUILTIN_SKILLS}


class TestTheRosterIsSearchedBeforeMinting(unittest.TestCase):
    def test_phrases_reach_the_skill_the_library_already_had(self):
        # Each of these minted a phantom before, every one rolling INT.
        cases = {
            "pick the lock": "lockpicking",
            "picking a lock": "lockpicking",
            "sneak past the guard": "stealth",
            "climb the wall": "athletics",
            "swim the channel": "athletics",
            "spot the ambush": "perception",
            "read the room": "insight",
            "track the cart": "survival",
            "calm the horse": "animal_handling",
            "forge the seal": "smithing",
            "haggle": "appraise",
            "persuade the captain": "persuasion",
            "recall the old war": "history",
        }
        for text, want in cases.items():
            with self.subTest(text=text):
                self.assertEqual(resolve_skill_code(text), want)

    def test_a_resolved_skill_brings_its_real_attribute(self):
        # The whole point: lockpicking is DEX, not INT.
        for text, attr in (
            ("pick the lock", "dexterity"),
            ("sneak past the guard", "dexterity"),
            ("climb the wall", "strength"),
            ("calm the horse", "wisdom"),
            ("persuade the captain", "charisma"),
        ):
            with self.subTest(text=text):
                code = resolve_skill_code(text)
                self.assertIsNotNone(code, f"{text!r} did not resolve")
                self.assertEqual(BUILT[code]["attribute"], attr)

    def test_exact_codes_and_names_still_resolve(self):
        for s in BUILTIN_SKILLS:
            with self.subTest(code=s["code"]):
                self.assertEqual(resolve_skill_code(s["code"]), s["code"])
                self.assertEqual(resolve_skill_code(s["name"]), s["code"])

    def test_a_genuinely_new_skill_resolves_to_nothing(self):
        # These have no home in the roster; the resolver must not invent one.
        # Pass the built-ins explicitly: the shared library file is written by
        # the minting tests below, and a skill that HAS been registered should
        # resolve -- that is the feature, not a leak.
        for text in ("hotwire the truck", "void surgery", "cranial shunt tuning"):
            with self.subTest(text=text):
                self.assertIsNone(resolve_skill_code(text, BUILTIN_SKILLS))


class TestTheResolverDoesNotGuess(unittest.TestCase):
    def test_ambiguous_tags_resolve_to_nothing(self):
        # These tags are owned by more than one skill. Picking a winner would be
        # a coin flip presented as a decision.
        owners: dict[str, set[str]] = {}
        for s in BUILTIN_SKILLS:
            for tag in s.get("tags") or []:
                owners.setdefault(tag.lower(), set()).add(s["code"])
        ambiguous = {t for t, o in owners.items() if len(o) > 1}
        self.assertTrue(ambiguous, "expected some tags to be shared")
        for tag in sorted(ambiguous):
            with self.subTest(tag=tag):
                got = resolve_skill_code(tag)
                # It may resolve via an exact code/name or the regex table, but
                # never via the ambiguous tag itself.
                if got is not None:
                    self.assertTrue(
                        got == tag
                        or got == tag.replace(" ", "_")
                        or any(tag == s["name"].lower() for s in BUILTIN_SKILLS if s["code"] == got)
                        or infer_check_from_action(tag) is not None,
                        f"{tag!r} resolved to {got!r} by ambiguous tag",
                    )

    def test_no_substring_matching(self):
        # "picking" contains "king"; "sector" contains "sect". The theme
        # detector shipped both bugs. This resolver must not repeat them.
        self.assertIsNone(resolve_skill_code("zzz"))
        for text in ("kingdom politics", "sector manifest"):
            with self.subTest(text=text):
                got = resolve_skill_code(text)
                self.assertNotIn(got, {"kin", "sect"})

    def test_empty_text_resolves_to_nothing(self):
        for text in ("", "   ", None):
            with self.subTest(text=text):
                self.assertIsNone(resolve_skill_code(text))


class TestAMintedSkillIsHonest(unittest.TestCase):
    def test_the_name_is_not_raw_snake_case(self):
        skill = register_or_adjust_skill({"name": "hotwire_engine", "source": "playthrough"})["skill"]
        self.assertEqual(skill["name"], "Hotwire Engine")

    def test_no_description_is_borrowed_from_an_unrelated_skill(self):
        # Every minted skill used to inherit "Related to General Check: ...".
        for raw in ("void_surgery", "slice_ice", "barter_scrap"):
            with self.subTest(raw=raw):
                skill = register_or_adjust_skill({"name": raw, "source": "playthrough"})["skill"]
                self.assertNotIn("Related to", skill.get("description") or "")
                self.assertNotIn(
                    "Fallback when no specialized skill fits",
                    skill.get("description") or "",
                )

    def test_a_supplied_description_is_still_kept(self):
        skill = register_or_adjust_skill(
            {"name": "Void Surgery", "description": "Cutting in vacuum without losing the patient.", "source": "playthrough"}
        )["skill"]
        self.assertEqual(skill["description"], "Cutting in vacuum without losing the patient.")


class TestTheTriggerTableIsReusable(unittest.TestCase):
    def test_the_table_is_module_level_and_non_empty(self):
        self.assertGreater(len(SKILL_TRIGGER_PATTERNS), 10)
        for pattern, code in SKILL_TRIGGER_PATTERNS:
            with self.subTest(code=code):
                self.assertIsInstance(pattern, str)
                self.assertIn(code, BUILT, f"trigger targets unknown skill {code!r}")

    def test_hoisting_did_not_change_auto_inference(self):
        # infer_check_from_action has existing callers; the hoist must be pure.
        for text, want in (
            ("i sneak past the guard", "stealth"),
            ("i haggle over the price", "appraise"),
            ("i attack the bandit", "melee"),
        ):
            with self.subTest(text=text):
                got = infer_check_from_action(text)
                self.assertIsNotNone(got)
                self.assertEqual(got.get("skill_code"), want)


class TestTheNarratorIsShownTheCatalogue(unittest.TestCase):
    """Finding 4: the packet carried the player's 12 skills, never the roster."""

    def test_the_packet_carries_the_skill_catalogue(self):
        from app.llm import _compact_turn_context

        compact = _compact_turn_context({"skills": [], "player": {}})
        self.assertIn("skill_catalog", compact)
        self.assertGreaterEqual(len(compact["skill_catalog"]), 40)
        for code in ("stealth", "lockpicking", "persuasion"):
            self.assertIn(code, compact["skill_catalog"])

    def test_the_catalogue_is_cheap_enough_to_send(self):
        # It rides in the packet, not SYSTEM_PROMPT: that prompt is already
        # ~9152 tokens against a shipped 8192 context default.
        from app.llm import _compact_turn_context, estimated_tokens

        codes = _compact_turn_context({"skills": []})["skill_catalog"]
        self.assertLess(estimated_tokens(", ".join(codes)), 400)

    def test_the_schema_no_longer_invites_invention(self):
        prompts = (ROOT / "app" / "prompts.py").read_text(encoding="utf-8", errors="replace")
        self.assertNotIn('"skill": "lying/speech/insight/etc"', prompts)
        self.assertIn("skill_catalog", prompts)


class TestStatSpellingsResolve(unittest.TestCase):
    """Finding 7: two alias tables covering the same six stats, disagreeing."""

    def test_both_tables_words_now_resolve(self):
        from app.skill_checks import canonical_stat_key

        for word, canon in (
            ("awareness", "wisdom"),      # was only in content_packs
            ("perception", "wisdom"),     # was only in skill_checks
            ("stamina", "constitution"),  # was only in content_packs
            ("might", "strength"),
            ("agility", "dexterity"),
            ("presence", "charisma"),
        ):
            with self.subTest(word=word):
                self.assertEqual(canonical_stat_key(word), canon)

    def test_an_alias_scores_the_stat_it_names(self):
        from app.skill_checks import _attr_score

        stats = {"strength": 14, "dexterity": 16, "constitution": 12,
                 "intelligence": 8, "wisdom": 11, "charisma": 9}
        self.assertEqual(_attr_score(stats, "awareness"), 11)
        self.assertEqual(_attr_score(stats, "stamina"), 12)
        self.assertEqual(_attr_score(stats, "zzz"), 10)


class TestEnumScalesLandOnTheNearestRung(unittest.TestCase):
    """Finding 6: off-roster synonyms all collapsed to the midpoint."""

    def test_obvious_synonyms_reach_their_rung(self):
        from app.setup_composer import sanitize_field_value

        for field, raw, want in (
            ("xp_growth_speed", "quick", "fast"),
            ("xp_growth_speed", "gradual", "slow"),
            ("xp_growth_speed", "glacial", "very slow"),
            ("new_skill_frequency", "often", "frequent"),
            ("new_skill_frequency", "uncommon", "rare"),
            ("narration_detail", "verbose", "expansive"),
            ("narration_detail", "detailed", "rich"),
            ("narration_detail", "terse", "concise"),
            ("difficulty", "deadly", "brutal"),
            ("difficulty", "casual", "easy"),
            ("difficulty", "tough", "hard"),
        ):
            with self.subTest(field=field, raw=raw):
                got, _reasons = sanitize_field_value(field, raw)
                self.assertEqual(got, want)

    def test_genuinely_middling_words_still_take_the_default(self):
        # "occasional" and "moderate" sit between two rungs. Guessing one would
        # be inventing a preference the model did not express.
        from app.setup_composer import sanitize_field_value

        self.assertEqual(sanitize_field_value("new_skill_frequency", "occasional")[0], "normal")
        self.assertEqual(sanitize_field_value("xp_growth_speed", "moderate")[0], "normal")

    def test_roster_values_pass_through_untouched(self):
        from app.setup_composer import FIELD_CONTRACTS, sanitize_field_value

        for field, contract in FIELD_CONTRACTS.items():
            for value in contract.get("allowed_values") or []:
                with self.subTest(field=field, value=value):
                    self.assertEqual(sanitize_field_value(field, value)[0], value)


class TestSlotsConsultTheirAcceptsList(unittest.TestCase):
    """Finding 5: 42 of 43 declared synonyms minted a duplicate slot."""

    def _conn(self):
        import json as _json
        import sqlite3

        from app.world import DEFAULT_EQUIPMENT_SLOTS

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            "CREATE TABLE equipment_slots (id INTEGER PRIMARY KEY, code TEXT, name TEXT, "
            "category TEXT, capacity INT, accepts TEXT, sort_order INT)"
        )
        for code, name, cat, cap, accepts, order in DEFAULT_EQUIPMENT_SLOTS:
            conn.execute(
                "INSERT INTO equipment_slots (code,name,category,capacity,accepts,sort_order) "
                "VALUES (?,?,?,?,?,?)",
                (code, name, cat, cap, _json.dumps(accepts), order),
            )
        return conn

    def test_every_unambiguous_accepted_word_finds_its_slot(self):
        from app.world import DEFAULT_EQUIPMENT_SLOTS, _slot_by_ref

        owners: dict[str, set[str]] = {}
        for code, _n, _c, _cap, accepts, _o in DEFAULT_EQUIPMENT_SLOTS:
            for word in accepts:
                owners.setdefault(word.lower(), set()).add(code)
        conn = self._conn()
        try:
            for word, own in owners.items():
                if len(own) > 1:
                    continue
                with self.subTest(word=word):
                    row = _slot_by_ref(conn, word, word)
                    self.assertIsNotNone(row, f"{word!r} did not find its slot")
                    self.assertIn(row["code"], own)
        finally:
            conn.close()

    def test_a_word_two_slots_accept_does_not_pick_one(self):
        # MAIN and OFF both take weapon/tool/focus. Choosing is a coin flip, so
        # these fall through to the DM-created-slot path, which is a feature.
        from app.world import _slot_by_ref

        conn = self._conn()
        try:
            for word in ("weapon", "tool", "focus"):
                with self.subTest(word=word):
                    self.assertIsNone(_slot_by_ref(conn, word, word))
        finally:
            conn.close()

    def test_code_and_name_still_win_first(self):
        from app.world import _slot_by_ref

        conn = self._conn()
        try:
            self.assertEqual(_slot_by_ref(conn, "FEET", None)["code"], "FEET")
            self.assertEqual(_slot_by_ref(conn, None, "Main Hand")["code"], "MAIN")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
