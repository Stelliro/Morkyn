"""app/ability_library.py: theme templates, the setup's theme mix, sampling, and the library that learns.

The library file and the database are pinned to a temp dir through the AI_RPG_* env.
"""
from __future__ import annotations

import collections
import json
import os
import random
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-ability-library-test-"))
_ENV = {
    "AI_RPG_DB": str(_TMP / "world.db"),
    "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
    "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
    "AI_RPG_CONSOLIDATED_FACTS": str(_TMP / "facts.jsonl"),
    "AI_RPG_CAMPAIGN_SLOTS": str(_TMP / "slots"),
    "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
    "AI_RPG_PACK_DIR": str(_TMP / "packs"),
    "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
    "AI_RPG_IDEA_BANK": str(_TMP / "idea_bank"),
    "AI_RPG_LAUNCHER_PREFS": str(_TMP / "launcher_prefs.json"),
    "AI_RPG_ABILITY_LIBRARY": str(_TMP / "ability_library.json"),
}
os.environ.update(_ENV)

from app import ability_growth, ability_library as lib, llm, world  # noqa: E402
from app.db import connect, db_path, init_db  # noqa: E402
from app.setup_composer import is_overused_seed_domain  # noqa: E402


def setUpModule() -> None:
    os.environ.update(_ENV)
    assert str(db_path()).startswith(str(_TMP)), f"test isolation failed: {db_path()!r}"
    assert str(lib.library_path()).startswith(str(_TMP)), f"test isolation failed: {lib.library_path()!r}"
    init_db()


def _reset_user_library() -> None:
    lib.library_path().unlink(missing_ok=True)


WUXIA = {"_randomize_idea": "Wuxia sect politics: cultivation realms, qi techniques, sect rivalries", "magic_level": "cultivation"}


class BuiltinTemplateTests(unittest.TestCase):
    def test_every_template_passes_the_ability_gate(self):
        """A template is a model-quality ability: same gate, on engine growth, as generation uses."""
        _, entries = lib.builtin()
        failing = []
        for entry in entries:
            card = ability_growth.build(dict(entry))
            report = llm.evaluate_ability_quality(card, require_strong_math=True, one_skillish=False)
            if not report.get("ok") or report.get("hard_fail") or is_overused_seed_domain(card["name"]):
                failing.append((entry["id"], report.get("hard_fail")))
        self.assertEqual(failing, [])

    def test_themes_are_full_and_names_unique(self):
        themes, entries = lib.builtin()
        self.assertGreaterEqual(len(themes), 17)
        per = collections.Counter(e["themes"][0] for e in entries)
        self.assertTrue(all(n >= 10 for n in per.values()), per)
        names = collections.Counter(lib.norm_name(e["name"]) for e in entries)
        self.assertEqual([n for n, c in names.items() if c > 1], [])
        for entry in entries:
            with self.subTest(template=entry["id"]):
                self.assertIn(ability_growth.template_id(entry["power_type"]), ability_growth.TEMPLATES)
                self.assertIn("supernatural", entry)
                self.assertNotRegex(str((entry.get("growth") or {}).get("grows") or ""), r"\d")


class ThemeMixTests(unittest.TestCase):
    def test_a_preset_idea_matches_its_theme(self):
        self.assertEqual(lib.theme_mix(WUXIA)[0][0], "wuxia")

    def test_a_custom_idea_mixes_themes(self):
        mix = dict(lib.theme_mix({"_randomize_idea": "a neon megacity where corporate sects teach qi cultivation through implants"}))
        self.assertIn("cyberpunk", mix)
        self.assertIn("wuxia", mix)
        self.assertAlmostEqual(sum(mix.values()), 1.0, places=2)

    def test_an_unknown_idea_falls_back_to_fantasy(self):
        self.assertEqual(lib.theme_mix({"_randomize_idea": "a quiet story about a lighthouse keeper"}), [("fantasy", 1.0)])


class SampleTests(unittest.TestCase):
    def setUp(self) -> None:
        _reset_user_library()

    def test_no_magic_worlds_get_no_supernatural_templates(self):
        setup = {"_randomize_idea": "cyberpunk megacity, chrome and fixers", "magic_level": "none"}
        for seed in range(10):
            picks = lib.sample(setup, 8, rng=random.Random(seed))
            self.assertTrue(picks)
            self.assertFalse(any(p.get("supernatural") for p in picks))

    def test_names_on_the_form_are_not_offered(self):
        picks = lib.sample(WUXIA, 12, exclude_names=["Meridian Tap"], rng=random.Random(2))
        self.assertNotIn("Meridian Tap", [p["name"] for p in picks])

    def test_a_much_used_template_comes_up_less(self):
        target = "wuxia:meridian-tap"
        lib.record_used([target] * 1)
        for _ in range(30):
            lib.record_used([target])
        hits = sum(1 for s in range(300) if target in [p["id"] for p in lib.sample(WUXIA, 4, rng=random.Random(s))])
        _reset_user_library()
        fresh = sum(1 for s in range(300) if target in [p["id"] for p in lib.sample(WUXIA, 4, rng=random.Random(s))])
        self.assertLess(hits, fresh / 3)


NEW_POWER = {
    "name": "Ink Tide Reading",
    "description": "Touch a flooded page and you can read what was written there before the water took it.",
    "cost": "Fingers stain black for a day",
    "power_type": "linear",
    "growth": {"pace": "steady", "start": "ordinary", "grows": "how long the page was under water"},
    "template_id": "new",
}


class LearnTests(unittest.TestCase):
    def setUp(self) -> None:
        _reset_user_library()

    def test_a_good_new_power_is_stored_with_the_setups_themes(self):
        stored = lib.learn([dict(NEW_POWER)], WUXIA)
        self.assertEqual([e["name"] for e in stored], ["Ink Tide Reading"])
        self.assertEqual(stored[0]["themes"][0], "wuxia")
        self.assertIn("Ink Tide Reading", [e["name"] for e in lib.all_entries()])
        self.assertEqual(lib.stats()["learned"], 1)

    def test_copies_pool_cards_and_weak_cards_are_not_stored(self):
        copy_of_template = {**NEW_POWER, "name": "Meridian Tapping"}  # near a built-in name
        pool_card = {**NEW_POWER, "name": "Brine Count", "_seed_pool": True}
        weak = {**NEW_POWER, "name": "Gloom", "description": "mysterious power"}
        adapted = {**NEW_POWER, "name": "Adapted Thing", "template_id": "wuxia:meridian-tap"}
        self.assertEqual(lib.learn([copy_of_template, pool_card, weak, adapted], WUXIA), [])
        self.assertFalse(lib.verify(copy_of_template)[0])
        self.assertTrue(lib.verify(copy_of_template)[1].startswith("copy_of:"))

    def test_the_same_new_power_is_stored_once(self):
        lib.learn([dict(NEW_POWER)], WUXIA)
        self.assertEqual(lib.learn([dict(NEW_POWER)], WUXIA), [])

    def test_a_learned_power_is_offered_later(self):
        lib.learn([dict(NEW_POWER)], WUXIA)
        seen = any("Ink Tide Reading" in [p["name"] for p in lib.sample(WUXIA, 8, rng=random.Random(s))] for s in range(40))
        self.assertTrue(seen)


class GenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        _reset_user_library()

    def _current(self):
        return {
            **WUXIA,
            "_locked_fields": [],
            "_field_context": {"count_min": 2, "count_max": 2, "requested_count": 2, "target_count": 2, "count_rolled": True},
            "difficulty": "normal",
            "special_abilities": [],
        }

    def test_templates_are_offered_used_and_new_powers_learned(self):
        prompts: list[dict] = []

        def fake_chat(system, user, **kwargs):
            payload = json.loads(user)
            prompts.append(payload)
            offered = payload.get("theme_templates") or []
            first = offered[0] if offered else {}
            return {"special_abilities": [
                {**{k: first.get(k) for k in ("name", "description", "cost", "power_type", "growth")},
                 "template_id": first.get("template_id")},
                dict(NEW_POWER),
            ]}

        with mock.patch.object(llm, "_chat_json", side_effect=fake_chat):
            result = llm.generate_setup_randomization("field:special_abilities", self._current())
        offered = prompts[0]["theme_templates"]
        self.assertEqual(len(offered), 8)
        self.assertTrue(all(t["template_id"].startswith("wuxia:") for t in offered))
        abilities = result["special_abilities"]
        self.assertEqual(abilities[0]["template_id"], offered[0]["template_id"])
        self.assertEqual(abilities[1]["template_id"], "new")
        self.assertEqual(result["ability_library"]["learned"], ["Ink Tide Reading"])
        usage = lib.load_user()["usage"]
        self.assertEqual(usage[offered[0]["template_id"]]["used"], 1)
        self.assertEqual(usage[offered[3]["template_id"]]["offered"], 1)

    def test_an_invented_template_id_counts_as_new(self):
        with mock.patch.object(llm, "_chat_json", return_value={"special_abilities": [
            {**NEW_POWER, "template_id": "wuxia:not-a-real-one"}, {**NEW_POWER, "name": "Salt Lantern Read",
                                                                    "description": "Hold a salt lamp to sense whether a room was visited today."}]}):
            result = llm.generate_setup_randomization("field:special_abilities", self._current())
        self.assertEqual({a["template_id"] for a in result["special_abilities"]}, {"new"})

    def test_a_fallback_teaches_nothing_and_fits_the_theme(self):
        with mock.patch.object(llm, "_chat_json", side_effect=llm.LlmError("model offline")):
            result = llm.generate_setup_randomization("field:special_abilities", self._current())
        self.assertTrue(result["fallback_used"])
        self.assertEqual(lib.stats()["learned"], 0)
        self.assertTrue(all(a.get("_seed_pool") for a in result["special_abilities"]))
        theme_cards = [a for a in result["special_abilities"] if str(a.get("template_id") or "").startswith("wuxia:")]
        self.assertTrue(theme_cards, [a["name"] for a in result["special_abilities"]])


class ChosenTests(unittest.TestCase):
    def setUp(self) -> None:
        _reset_user_library()

    def test_starting_a_game_counts_its_library_abilities(self):
        world.start_playthrough({
            "player_name": "Wren", "start_location": "Low Gate", "special_ability_origin": "both", "magic_level": "cultivation",
            "special_abilities": [
                {"name": "Meridian Tap", "description": "Touch a point on someone's arm to numb it for a minute.",
                 "power_type": "breakthrough", "template_id": "wuxia:meridian-tap"},
                {"name": "Sect Ledger Memory", "description": "Read a sect roster once and recall every name on it.",
                 "power_type": "linear"},
            ],
        })
        usage = lib.load_user()["usage"]
        self.assertEqual(usage["wuxia:meridian-tap"]["chosen"], 1)
        self.assertEqual(usage["wuxia:sect-ledger-memory"]["chosen"], 1, "a matching name counts without an id")


if __name__ == "__main__":
    unittest.main()
