"""Setup choices stay short. The written rule is a SQLite template, made before the opening."""

from __future__ import annotations

import gc
import os
import tempfile
import unittest
import warnings
from pathlib import Path
from unittest import mock

from app.db import connect, init_db
from app.prompts import SYSTEM_PROMPT, build_user_prompt
from app.setting_templates import (
    TEMPLATE_SPECS,
    choice_parts,
    cloud_templates_allowed,
    fallback_rule,
    refresh_setting_templates_from_model,
    rule_covers_choice,
    store_setting_templates,
)
from app.turn_dsl import DSL_SYSTEM_PROMPT, build_dsl_user_prompt
from app.world import _rank_labels, export_world, import_world, start_playthrough

_ENV = (
    "AI_RPG_DB",
    "AI_RPG_CAMPAIGN_SLOTS",
    "AI_RPG_MODEL_TRACE_DIR",
    "AI_RPG_HISTORY_SUMMARY",
    "AI_RPG_SOURCE_INDEX",
    "AI_RPG_CONSOLIDATED_FACTS",
    "AI_RPG_SETTING_TEMPLATES",
)


class SettingTemplateTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="morkyn-setting-templates-")
        root = Path(self._tmp.name)
        self._saved = {key: os.environ.get(key) for key in _ENV}
        os.environ["AI_RPG_DB"] = str(root / "world.db")
        os.environ["AI_RPG_CAMPAIGN_SLOTS"] = str(root / "slots")
        os.environ["AI_RPG_MODEL_TRACE_DIR"] = str(root / "traces")
        os.environ["AI_RPG_HISTORY_SUMMARY"] = str(root / "history.jsonl")
        os.environ["AI_RPG_SOURCE_INDEX"] = str(root / "source")
        os.environ["AI_RPG_CONSOLIDATED_FACTS"] = str(root / "facts.jsonl")
        os.environ["AI_RPG_SETTING_TEMPLATES"] = "0"
        self.assertTrue(str(os.environ["AI_RPG_DB"]).startswith(str(root)))

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)
            gc.collect()
        self._tmp.cleanup()

    def test_every_catalog_sample_has_a_rule_that_names_the_choice(self):
        self.assertIn("rank_scale", {spec["key"] for spec in TEMPLATE_SPECS})
        for spec in TEMPLATE_SPECS:
            rule = fallback_rule(spec["key"], spec["sample"])
            self.assertTrue(
                rule_covers_choice(spec["key"], spec["sample"], rule),
                spec["key"],
            )
            self.assertNotIn("near-useless", rule.lower())
            self.assertLess(len(rule), len(spec["sample"]) + 800)

    def test_f_to_sss_names_every_rung_and_a_short_ladder_does_not_grow(self):
        full = fallback_rule("rank_scale", "F,E,D,C,B,A,S,SS,SSS")
        self.assertTrue(rule_covers_choice("rank_scale", "F,E,D,C,B,A,S,SS,SSS", full))
        self.assertIn("untrained", full.lower())
        short = fallback_rule("rank_scale", "D,C,B,A,S")
        self.assertIn("shorter ladder", short.lower())
        self.assertIn("Do not add F", short)
        named = fallback_rule("rank_scale", "Common,Trained,Veteran,Elite,Mythic")
        self.assertIn("Mythic", named)
        self.assertIn("letter ranks", named.lower())
        custom = fallback_rule("rank_scale", "Novice, Adept, Master")
        self.assertTrue(rule_covers_choice("rank_scale", "Novice, Adept, Master", custom))
        self.assertIn("adept sits above novice and below master", custom.lower())

    def test_custom_list_becomes_one_preset_per_label(self):
        choice = "common, uncommon, rare, epic, legendary, unique and unknown"
        self.assertLess(len(choice), 100)
        self.assertEqual(
            [part.lower() for part in choice_parts(choice)],
            ["common", "uncommon", "rare", "epic", "legendary", "unique", "unknown"],
        )
        self.assertEqual(choice_parts("android, handmade"), ["android", "handmade"])
        self.assertEqual(
            [part.lower() for part in choice_parts("earned and uncommon")],
            ["earned and uncommon"],
        )
        self.assertEqual(
            [part.lower() for part in choice_parts("earned and uncommon, scarce mundane")],
            ["earned and uncommon", "scarce mundane"],
        )

        rule = fallback_rule("rank_scale", choice)
        self.assertTrue(rule_covers_choice("rank_scale", choice, rule))
        self.assertNotIn("unique and unknown", rule.lower())
        self.assertNotIn("near-useless", rule.lower())
        self.assertNotIn("compounding", rule.lower())
        self.assertNotIn("hour per level", rule.lower())
        for label in ("common", "uncommon", "rare", "epic", "legendary", "unique", "unknown"):
            self.assertIn(label, rule.lower())
        self.assertIn("common is the bottom of this ladder", rule.lower())
        self.assertIn("unknown is the top of this ladder", rule.lower())
        self.assertIn("uncommon sits above common and below rare", rule.lower())
        self.assertIn("unique sits above legendary and below unknown", rule.lower())
        self.assertEqual(
            _rank_labels({"rank_scale": choice}),
            ["COMMON", "UNCOMMON", "RARE", "EPIC", "LEGENDARY", "UNIQUE", "UNKNOWN"],
        )
        named = fallback_rule("rank_scale", "Common,Trained,Veteran,Elite,Mythic")
        self.assertIn("letter ranks", named.lower())

        economy = "harbor tithes, temple coin and road barter"
        economy_rule = fallback_rule("economy", economy)
        self.assertTrue(rule_covers_choice("economy", economy, economy_rule))
        self.assertNotIn("follow this", economy_rule.lower())
        self.assertNotIn("f, e, d", economy_rule.lower())
        for label in ("harbor tithes", "temple coin", "road barter"):
            self.assertIn(label, economy_rule.lower())
        self.assertIn("does not erase", fallback_rule("death_rules", "downed, not deleted").lower())
        self.assertIn("stay uncommon", fallback_rule("loot_rarity", "earned and uncommon").lower())

        written = (
            "Ranks run from low to high: common, uncommon, rare, epic, legendary, unique, unknown. "
            "Common is the bottom. Uncommon is the next step up. Rare is scarce. "
            "Epic is a feat. Legendary is a story people repeat. Unique is one of a kind. "
            "Unknown is the top of this ladder. A higher rung than the player is stronger than the player."
        )
        glued = (
            "Ranks run from low to high: common, uncommon, rare, epic, legendary, then unique and unknown. "
            "Each step up is clearly stronger than the step below. A higher rung than the player is stronger."
        )
        omitted = (
            "Ranks run from low to high: common, uncommon, rare, epic, legendary, unique. "
            "Unique is the top of this ladder. Each step up is clearly stronger than the player."
        )
        self.assertTrue(rule_covers_choice("rank_scale", choice, written))
        self.assertFalse(rule_covers_choice("rank_scale", choice, glued))
        self.assertFalse(rule_covers_choice("rank_scale", choice, omitted))

        init_db()
        conn = connect()
        try:
            with conn:
                kept = store_setting_templates(
                    conn,
                    {"rank_scale": choice},
                    {"rank_scale": written},
                )
                self.assertEqual(kept["rank_scale"]["source"], "llm")
                self.assertEqual(kept["rank_scale"]["choice"], choice)
                rejected = store_setting_templates(
                    conn,
                    {"rank_scale": choice},
                    {"rank_scale": omitted},
                )
                self.assertEqual(rejected["rank_scale"]["source"], "fallback")
                self.assertIn("unknown is the top", rejected["rank_scale"]["rule"].lower())
                self.assertNotIn("unique and unknown", rejected["rank_scale"]["rule"].lower())
                glued_row = store_setting_templates(
                    conn,
                    {"rank_scale": choice},
                    {"rank_scale": glued},
                )
                self.assertEqual(glued_row["rank_scale"]["source"], "fallback")
        finally:
            conn.close()

        state = start_playthrough({"player_name": "Mara Vale", "rank_scale": choice})
        options = (state.get("settings") or {}).get("playthrough_options") or {}
        self.assertEqual(options.get("rank_scale"), choice)
        stored = (options.get("setting_templates") or {}).get("rank_scale") or {}
        self.assertEqual(stored.get("choice"), choice)
        self.assertEqual(stored.get("source"), "fallback")
        self.assertIn("unknown is the top", (stored.get("rule") or "").lower())
        self.assertNotIn("unique and unknown", (stored.get("rule") or "").lower())

    def test_a_model_rule_is_kept_only_when_it_covers_the_choice(self):
        init_db()
        ladder = "F,E,D,C,B,A,S,SS,SSS"
        written = (
            "Ranks run from low to high: F, E, D, C, B, A, S, SS, SSS. "
            "F is untrained. E has some practice. D is competent. C is skilled. "
            "B is notable. A is an expert. S is exceptional. SS is rare mastery. "
            "SSS is the top of this ladder in a scarce frontier. "
            "A higher rung than the player is stronger than the player."
        )
        missing = (
            "Ranks run from low to high: F, E, D, C, B, A, S, SS. "
            "Each step up is clearly stronger than the player."
        )
        essay = written + " This is a near-useless compounding hour per level."
        conn = connect()
        try:
            with conn:
                packed = store_setting_templates(
                    conn,
                    {"rank_scale": ladder, "economy": "scarce, guild-controlled"},
                    {"rank_scale": written, "economy": "Prices are scarce only."},
                )
        finally:
            conn.close()
        self.assertEqual(packed["rank_scale"]["source"], "llm")
        self.assertEqual(packed["rank_scale"]["choice"], ladder)
        self.assertIn("scarce frontier", packed["rank_scale"]["rule"])
        self.assertEqual(packed["economy"]["source"], "fallback")
        self.assertIn("guild", packed["economy"]["rule"].lower())
        conn = connect()
        try:
            with conn:
                rejected = store_setting_templates(
                    conn,
                    {"rank_scale": ladder},
                    {"rank_scale": missing},
                )
                essay_kept = store_setting_templates(
                    conn,
                    {"rank_scale": ladder},
                    {"rank_scale": essay},
                )
        finally:
            conn.close()
        self.assertEqual(rejected["rank_scale"]["source"], "fallback")
        self.assertIn("SSS", rejected["rank_scale"]["rule"])
        self.assertEqual(essay_kept["rank_scale"]["source"], "fallback")
        self.assertNotIn("near-useless", essay_kept["rank_scale"]["rule"].lower())

    def test_start_stores_the_rule_and_leaves_the_ladder_short(self):
        init_db()
        state = start_playthrough(
            {
                "player_name": "Mara Vale",
                "world_style": "frontier dark fantasy",
                "rank_scale": "F,E,D,C,B,A,S,SS,SSS",
                "economy": "scarce",
                "quest_style": "emergent",
            }
        )
        options = (state.get("settings") or {}).get("playthrough_options") or {}
        self.assertEqual(options.get("rank_scale"), "F,E,D,C,B,A,S,SS,SSS")
        templates = options.get("setting_templates") or {}
        rank = templates.get("rank_scale") or {}
        self.assertEqual(rank.get("choice"), "F,E,D,C,B,A,S,SS,SSS")
        self.assertEqual(rank.get("source"), "fallback")
        self.assertIn("SSS", rank.get("rule") or "")
        self.assertGreater(len(rank.get("rule") or ""), len(rank.get("choice") or ""))
        self.assertIn("economy", templates)
        self.assertIn("check_difficulty", templates)
        conn = connect()
        try:
            row = conn.execute(
                "SELECT choice, rule, source FROM setting_templates WHERE key = 'rank_scale'"
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["source"], "fallback")
            self.assertIn("F", row["rule"])
        finally:
            conn.close()

        exported = export_world()
        saved = exported["tables"].get("setting_templates") or []
        self.assertTrue(any(item.get("key") == "rank_scale" for item in saved))
        import_world(exported)
        conn = connect()
        try:
            again = conn.execute(
                "SELECT rule FROM setting_templates WHERE key = 'rank_scale'"
            ).fetchone()
            self.assertIn("SSS", again["rule"])
        finally:
            conn.close()

        start_playthrough({"player_name": "Mara Vale", "rank_scale": "D,C,B,A,S"})
        conn = connect()
        try:
            rows = conn.execute(
                "SELECT choice, rule FROM setting_templates WHERE key = 'rank_scale'"
            ).fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["choice"], "D,C,B,A,S")
            self.assertIn("shorter ladder", rows[0]["rule"].lower())
        finally:
            conn.close()

    def test_fallback_flag_does_not_call_the_model(self):
        self.assertFalse(cloud_templates_allowed())
        init_db()
        start_playthrough({"player_name": "Mara Vale", "rank_scale": "F,E,D,C,B,A,S,SS,SSS"})
        with mock.patch(
            "app.setting_templates.ask_model",
            side_effect=AssertionError("model called"),
        ):
            result = refresh_setting_templates_from_model()
        self.assertFalse(result.get("called"))
        conn = connect()
        try:
            row = conn.execute(
                "SELECT source FROM setting_templates WHERE key = 'rank_scale'"
            ).fetchone()
            self.assertEqual(row["source"], "fallback")
        finally:
            conn.close()

    def test_prompts_tell_the_model_to_obey_the_stored_rule(self):
        self.assertIn("setting_templates", SYSTEM_PROMPT)
        self.assertIn("setting_templates", DSL_SYSTEM_PROMPT)
        context = {
            "settings": {
                "playthrough_options": {
                    "rank_scale": "F,E,D,C,B,A,S,SS,SSS",
                    "setting_templates": {
                        "rank_scale": {
                            "choice": "F,E,D,C,B,A,S,SS,SSS",
                            "rule": "Ranks run from low to high: F, E, D, C, B, A, S, SS, SSS.",
                            "source": "llm",
                        }
                    },
                }
            }
        }
        prose = build_user_prompt(context, "look around")
        dsl = build_dsl_user_prompt(context, "look around")
        self.assertIn("setting_templates", prose)
        self.assertIn("use only the rungs", dsl.lower())
