"""
Playtest #1: Custom Proficiencies randomized into poetic slogans.

The field's help text promises "custom proficiencies and training-rule phrases
(seed skill name, tracking style, hard limits)". A random fill came back as
twelve verb phrases ("weave light, master the dance of shadows, earn trust
through deeds, ... braid destiny"): the asks only said "skill discovery,
training limits, progression rules, or named proficiencies", the field rolled
before the backstory and the powers it should come from, and the text then
rode whole into the game.

These tests check:
  - every ask that writes custom_skills carries the shape the help text
    promises, with no sample names, and the roll sees the character;
  - custom_skills now rolls after character_backstory and special_abilities;
  - the post-start pass validates SKILL/RULE lines on structure (a sentence or
    motto is not a name, rank on the scale and within this start, tracking and
    limit present, unique names), mirrors skills into player_skills, stores
    rules as world_facts, and rewrites custom_skills as a summary of the rows.
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
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-proficiencies-"))
os.environ.update(isolated_data_env(str(_TMP)))
os.environ.update(
    {
        "AI_RPG_PACK_DIR": str(_TMP / "packs"),
        "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
        "AI_RPG_POST_START_MODEL": "off",
    }
)

from app import db, llm, world  # noqa: E402
from app import proficiencies as prof  # noqa: E402
from app import world_facts as wf  # noqa: E402
from app.db import connect  # noqa: E402
from app.setup_composer import COMPOSER_FIELD_ORDER, CUSTOM_SKILLS_SHAPE, field_contract  # noqa: E402

# The playtest's random fill, as logged in docs/PLAYTEST_ISSUES.md #1.
SLOGANS = "weave light, master the dance of shadows, earn trust through deeds, braid destiny"

SETUP = {
    "world_style": "frontier dark fantasy",
    "tech_level": "medieval",
    "magic_level": "rare",
    "rank_scale": "F,E,D,C,B,A,S,SS,SSS",
    "skill_style": "training-heavy",
    "proficiency_access": "basic attempts allowed, mastery needs a mentor",
    "character_backstory": "A ferry hand who spent ten years poling barges through flooded marsh channels.",
    "special_abilities": [{"name": "Current Sense", "description": "Feels the pull of moving water nearby."}],
}


def setUpModule():
    os.environ.update(isolated_data_env(str(_TMP)))
    assert str(db.db_path()).startswith(str(_TMP)), db.db_path()
    db.init_db()


def _capture_prompt(group: str, current: dict) -> dict:
    captured: dict = {}

    def fake_chat(system, user, **kwargs):
        captured["user"] = user
        raise RuntimeError("stop after prompt build")

    original = llm._chat_json
    llm._chat_json = fake_chat
    try:
        llm.generate_setup_randomization(group, current)
    except Exception:
        pass
    finally:
        llm._chat_json = original
    return json.loads(captured["user"])


class TheAskSpellsOutTheShape(unittest.TestCase):
    def test_shape_names_the_parts_the_help_text_promises(self):
        for part in ("named proficiency", "starting rank on rank_scale", "how its progress is tracked",
                     "hard limit", "training rule", "character_backstory", "special_abilities", "tech_level"):
            self.assertIn(part, CUSTOM_SKILLS_SHAPE)

    def test_single_field_roll_carries_shape_and_character(self):
        prompt = _capture_prompt("field:custom_skills", dict(SETUP, custom_skills=SLOGANS))
        self.assertEqual(prompt["field_contract"]["shape"], CUSTOM_SKILLS_SHAPE)
        self.assertIn("field_contract.shape", prompt["field_note"])
        self.assertIn("character_backstory", prompt["nearby_setup"])
        self.assertIn("special_abilities", prompt["nearby_setup"])
        for key in ("tech_level", "world_style", "rank_scale", "magic_level"):
            self.assertIn(key, prompt["nearby_setup"])
        # The whole roll prompt stays near its old size; a doubled prompt
        # doubled the roll time on Qwen3 8B against a 45s timeout. The
        # per-call draws (proficiency names, idea sparks) make the size vary:
        # 7055-7237 over 60 rolls, so 7200 failed about one run in nine.
        self.assertLess(len(json.dumps(prompt)), 7400)

    def test_group_roll_contract_carries_shape(self):
        contracts = llm._field_contracts_for_prompt(["custom_skills"], dict(SETUP), set())
        self.assertEqual(contracts["custom_skills"]["shape"], CUSTOM_SKILLS_SHAPE)

    def test_no_sample_domains_or_names_in_the_ask(self):
        prompt = _capture_prompt("field:custom_skills", dict(SETUP))
        note = prompt["field_note"]
        for pasted in ("weather", "observation", "ropework", "barter", "Digging"):
            self.assertNotIn(pasted, note)
        self.assertNotIn("Digging", CUSTOM_SKILLS_SHAPE)
        self.assertNotIn("Digging", prof._SETTLE_SYSTEM)

    def test_custom_skills_rolls_after_the_character_and_powers(self):
        order = list(COMPOSER_FIELD_ORDER)
        for parent in ("character_backstory", "special_abilities", "rank_scale", "tech_level"):
            self.assertLess(order.index(parent), order.index("custom_skills"), parent)
        powers = order[order.index("special_abilities"):]
        self.assertEqual(powers, ["special_abilities", "custom_skills"])


def _fresh(options: dict | None = None) -> dict:
    opts = dict(SETUP, custom_skills=SLOGANS, **(options or {}))
    with connect() as conn:
        wf.ensure_world_fact_tables(conn)
        wf.clear_world_facts(conn)
        prof.clear_proficiencies(conn)
        conn.execute("DELETE FROM player_skills")
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('playthrough_options', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (json.dumps(opts),),
        )
    return opts


class TheEngineValidatesStructure(unittest.TestCase):
    def test_slogans_as_names_are_refused(self):
        for slogan in ("master the dance of shadows", "earn trust through deeds", "Walk With The River"):
            self.assertIn("name reads as a sentence, not a skill name", prof.name_shape_errors(slogan), slogan)
        self.assertEqual(prof.name_shape_errors("Barge Poling"), [])
        self.assertEqual(prof.name_shape_errors("Lore of Tides"), [])
        self.assertTrue(prof.name_shape_errors("Reading the currents of the deep marsh"))

    def test_rank_cap_follows_the_start(self):
        labels = prof.rank_labels({"rank_scale": "F,E,D,C,B,A,S,SS,SSS"})
        # Playtest #35: an ordinary start is the lowest quarter (D), not the midpoint (B).
        self.assertEqual(prof.start_rank_cap({}, labels), 2)
        weak = {"session_theme": {"power_fantasy": {"start_power": "near_useless"}}}
        # Playtest #22: a weak, seed or compounding start keeps to the bottom rank.
        self.assertEqual(prof.start_rank_cap(weak, labels), 0)
        strong = {"session_theme": {"power_fantasy": {"start_power": "strong"}}}
        self.assertEqual(prof.start_rank_cap(strong, labels), 8)

    def test_settlement_keeps_rows_and_rewrites_the_text(self):
        opts = _fresh()
        content = "\n".join([
            # A verb phrase whose object is not a skill (playtest #22 turns
            # "master the dance of shadows" into Dance of Shadows instead).
            "SKILL|earn trust through deeds|F|practice at night|cannot hide in daylight",
            "SKILL|Barge Poling|E|each hard crossing logged by the ferry master|no use in open sea",
            "SKILL|Marsh Reckoning|Q|walking new channels|none past the delta",
            "SKILL|Rope Splicing|SS|repairs done on the job|no load over one ton",
            "SKILL|barge poling|F|again|again",
            "SKILL|Current Reading|F||",
            "RULE|Mentors gate mastery|Ranks above D need a named mentor met in play.",
            "Some prose the parser ignores.",
        ])
        with connect() as conn:
            report = prof.apply_settlement(conn, content, opts)
        self.assertEqual(report["accepted"], {"skills": 3, "rules": 1})
        reasons = " ".join(report["rejected"])
        self.assertIn("a verb phrase that names no skill", reasons)
        # Off the scale: the engine starts it at the lowest rank. Over the
        # start's cap: kept at the cap. Neither is lost.
        self.assertEqual(
            report["adjusted"],
            [
                "SKILL Marsh Reckoning: rank 'Q' not on the scale, set to F",
                "SKILL Rope Splicing: start rank lowered to D",
                # The model's title named words the rule does not say.
                "RULE Mentors gate mastery: titled Mentor Limit from its text",
            ],
        )
        self.assertIn("duplicate", reasons)
        self.assertIn("tracking missing", reasons)
        with connect() as conn:
            rows = prof.proficiency_rows(conn)
            skills = {row["name"]: dict(row) for row in conn.execute("SELECT * FROM player_skills").fetchall()}
            rules = prof.proficiency_rules(conn)
            stored = json.loads(conn.execute("SELECT value FROM settings WHERE key = 'playthrough_options'").fetchone()["value"])
        self.assertEqual([(r["name"], r["start_rank"]) for r in rows], [("Barge Poling", "E"), ("Marsh Reckoning", "F"), ("Rope Splicing", "D")])
        self.assertIn("Barge Poling", skills)
        self.assertEqual(skills["Barge Poling"]["value"], prof.skill_value_for_rank(1))
        self.assertIn("Start rank E", skills["Barge Poling"]["notes"])
        self.assertEqual(len(rules), 1)
        self.assertEqual(stored["custom_skills_setup"], SLOGANS)
        self.assertTrue(stored["custom_skills"].startswith("Barge Poling (start rank E; tracked by"))
        self.assertIn("Ranks above D need a named mentor met in play", stored["custom_skills"])
        self.assertNotIn("braid destiny", stored["custom_skills"])

    def test_live_probe_fragment_rules_are_refused(self):
        # Qwen3 8B's answer to a rolled string (live probe, 2026-10-05): RULE
        # lines that were the pieces of the skill phrases, listed before them.
        opts = _fresh()
        content = "\n".join([
            "RULE|Training|first lesson, successful attempts, no self-taught skills",
            "RULE|Crossings|can't navigate burned crossings, tracked by barge poling experience",
            "SKILL|Ferry Craft|C|by barge poling experience|can't navigate burned crossings",
            "RULE|Mentors|New proficiencies need a mentor's first lesson before any practice counts.",
        ])
        with connect() as conn:
            report = prof.apply_settlement(conn, content, opts)
            row = prof.proficiency_rows(conn)[0]
        self.assertEqual(report["accepted"], {"skills": 1, "rules": 1})
        reasons = " ".join(report["rejected"])
        self.assertIn("a list of fragments", reasons)
        self.assertIn("restates a stored fact", reasons)
        self.assertEqual(row["tracking"], "barge poling experience")

    def test_live_probe_doubled_name_lines_and_rank_limits(self):
        # Qwen3 8B, live: the SKILL head replaced by the name, and a bare rank
        # as the limit.
        opts = _fresh({"rank_scale": "Common,Trained,Veteran,Elite,Mythic"})
        content = "Etiquette|Etiquette|Trained|social interactions|Elite"
        with connect() as conn:
            report = prof.apply_settlement(conn, content, opts)
            row = prof.proficiency_rows(conn)[0]
        self.assertEqual(report["accepted"]["skills"], 1)
        self.assertEqual((row["start_rank"], row["hard_limit"]), ("Trained", "capped at rank Elite"))

    def test_a_rule_copied_from_the_settings_is_refused(self):
        opts = _fresh()
        with connect() as conn:
            report = prof.apply_settlement(
                conn, "RULE|Access|Basic attempts are allowed but mastery needs a mentor.", opts
            )
        self.assertEqual(report["accepted"]["rules"], 0)
        self.assertIn("restates a stored fact", report["rejected"][0])

    def test_word_rank_scale_keeps_its_spelling(self):
        opts = _fresh({"rank_scale": "Common,Trained,Veteran,Elite,Mythic"})
        with connect() as conn:
            report = prof.apply_settlement(conn, "SKILL|Herb Alchemy|common|recipes replicated|needs a master's approval", opts)
            row = prof.proficiency_rows(conn)[0]
        self.assertEqual(report["accepted"]["skills"], 1)
        self.assertEqual(row["start_rank"], "Common")

    def test_nothing_accepted_leaves_the_text(self):
        opts = _fresh()
        with connect() as conn:
            report = prof.apply_settlement(conn, "SKILL|braid destiny with the stars|F|x|y", opts)
            stored = json.loads(conn.execute("SELECT value FROM settings WHERE key = 'playthrough_options'").fetchone()["value"])
        self.assertEqual(report["accepted"], {"skills": 0, "rules": 0})
        self.assertEqual(stored["custom_skills"], SLOGANS)

    def test_existing_seed_skill_keeps_its_value(self):
        opts = _fresh()
        with connect() as conn:
            conn.execute("INSERT INTO player_skills (name, value, notes) VALUES ('Barge Poling', 3, '')")
            prof.apply_settlement(conn, "SKILL|Barge Poling|F|hard crossings|no open sea", opts)
            row = conn.execute("SELECT value, notes FROM player_skills WHERE name = 'Barge Poling'").fetchone()
            count = conn.execute("SELECT COUNT(*) AS n FROM player_skills").fetchone()["n"]
        self.assertEqual((row["value"], count), (3, 1))
        self.assertIn("tracked by hard crossings", row["notes"])


class ThePostStartPass(unittest.TestCase):
    def test_registered_after_world_facts(self):
        names = [name for name, _ in wf._POST_START_PASSES]
        self.assertLess(names.index("world_facts"), names.index("proficiencies"))

    def test_settle_prompt_carries_character_world_and_scale(self):
        user = json.loads(prof.settle_prompt(dict(SETUP, custom_skills=SLOGANS), ["Barge Poling"]))
        self.assertEqual(user["custom_proficiency_text"], SLOGANS)
        self.assertEqual(user["highest_start_rank"], "D")
        self.assertEqual(user["character"]["abilities"][0]["name"], "Current Sense")
        self.assertEqual(user["character"]["skills_already_recorded"], ["Barge Poling"])
        self.assertEqual(user["world"]["tech_level"], "medieval")

    def test_start_then_pass_settles_rows(self):
        world.start_playthrough(
            dict(SETUP, custom_skills=SLOGANS, player_name="Harrow Ames", special_ability_origin="none")
        )
        calls: list[str] = []

        def fake_content(system, user, **kwargs):
            calls.append(system)
            if system is prof._SETTLE_SYSTEM:
                return "SKILL|Barge Poling|F|hard crossings logged|no open sea\nRULE|Light needs a teacher|Light craft is learned only from a shrine keeper."
            return ""

        original_allowed, original_content = wf.post_start_model_allowed, llm._chat_content
        wf.post_start_model_allowed = lambda: True
        llm._chat_content = fake_content
        try:
            report = wf.run_post_start_passes()
        finally:
            wf.post_start_model_allowed, llm._chat_content = original_allowed, original_content
        self.assertEqual(report["passes"]["proficiencies"]["accepted"], {"skills": 1, "rules": 1})
        state = world.get_state()
        options = state["settings"]["playthrough_options"]
        self.assertTrue(options["custom_skills"].startswith("Barge Poling (start rank F"))
        self.assertEqual(options["custom_skills_setup"], SLOGANS)
        self.assertIn("Barge Poling", [skill["name"] for skill in state["skills"]])

    def test_a_new_playthrough_drops_the_last_rows(self):
        _fresh()
        with connect() as conn:
            prof.apply_settlement(conn, "SKILL|Barge Poling|F|hard crossings|no open sea", dict(SETUP))
        world.start_playthrough(dict(SETUP, custom_skills="", player_name="Harrow Ames", special_ability_origin="none"))
        with connect() as conn:
            self.assertEqual(prof.proficiency_rows(conn), [])

    def test_table_rides_in_a_save(self):
        self.assertIn("player_proficiencies", world.WORLD_TABLES)
        self.assertIn("player_proficiencies", world.RESTORE_ORDER)


if __name__ == "__main__":
    unittest.main()
