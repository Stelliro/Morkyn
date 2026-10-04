"""
Playtest #8: world settings as small engine rows, fetched by relevance.

The 2026-10-05 game (data/world.db, playthrough_options) set up six peoples
and one race magic rule, "Only elves and Spirit touched/spirits have magic."
The turn packet carried world_races as a label and dropped custom_style and
race_magic_rules entirely, so nothing told the scene writer that Aria, a human
baker, has no magic. app/world_facts.py splits those strings into race and
fact rows at start, validates every row (deterministic or model), and hands
the draft a budgeted handful: the races of the people present, then lore the
turn's words touch.

These tests use the logged game's strings as fixtures and check:
  - the tables exist after init_db and ride along in a save;
  - the split gives one row per people with the right magic access;
  - validation refuses bad enums, long text, unknown links and race codes;
  - the relevance fetch picks the present NPC's race and the rule that names it;
  - start_playthrough seeds the rows and the draft packet carries them.
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-world-facts-"))
os.environ.update(isolated_data_env(str(_TMP)))
os.environ.update(
    {
        "AI_RPG_PACK_DIR": str(_TMP / "packs"),
        "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
        "AI_RPG_POST_START_MODEL": "off",
    }
)

from app import db, world  # noqa: E402
from app import world_facts as wf  # noqa: E402
from app.db import connect  # noqa: E402

# Copied from the logged game's playthrough_options (read-only).
LOGGED_OPTIONS = {
    "world_style": "frontier dark fantasy",
    "magic_level": "rare",
    "world_races": "human, elf, dwarf, orc, beastfolk, spirit-touched",
    "race_magic_enabled": True,
    "race_magic_rarity": "common for specific races",
    "race_magic_rules": "Only elves and Spirit touched/spirits have magic.",
    "race_ability_rules": "",
    "custom_style": (
        "In a frontier dark fantasy land, harsh climates and sparse settlements harbor power that can be "
        "earned through risk and training. Magic is rare but present, shaping daily life and earned through "
        "trials. The mood is grounded and adventurous, with local stakes and fair challenges."
    ),
    "faction_pressure": "local disputes, hidden cults",
}


def setUpModule():
    os.environ.update(isolated_data_env(str(_TMP)))
    assert str(db.db_path()).startswith(str(_TMP)), db.db_path()
    db.init_db()


def _seed(options=None):
    with connect() as conn:
        return wf.seed_from_options(conn, dict(options or LOGGED_OPTIONS))


def _races():
    with connect() as conn:
        return {row["name"]: dict(row) for row in conn.execute("SELECT * FROM world_races").fetchall()}


class TablesTest(unittest.TestCase):
    def test_tables_created_by_init_db(self):
        with connect() as conn:
            names = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        self.assertIn("world_races", names)
        self.assertIn("world_facts", names)

    def test_tables_ride_along_in_a_save(self):
        self.assertIn("world_races", world.WORLD_TABLES)
        self.assertIn("world_facts", world.WORLD_TABLES)
        self.assertIn("world_races", world.RESTORE_ORDER)
        # Not replace-only: an old slot must not inherit the last world's rows.
        self.assertNotIn("world_races", world._REPLACE_ONLY_WHEN_EXPORTED)


class SplitTest(unittest.TestCase):
    def test_logged_race_list_is_one_row_per_people(self):
        report = _seed()
        self.assertEqual(report["races"], 6)
        self.assertEqual(report["rejected"], [])
        self.assertEqual(set(_races()), {"human", "elf", "dwarf", "orc", "beastfolk", "spirit-touched"})

    def test_only_rule_opens_magic_to_named_peoples_and_closes_the_rest(self):
        _seed()
        races = _races()
        self.assertEqual(races["elf"]["magic_access"], "innate")
        self.assertEqual(races["spirit-touched"]["magic_access"], "innate")
        for name in ("human", "dwarf", "orc", "beastfolk"):
            self.assertEqual(races[name]["magic_access"], "none", name)

    def test_rule_sentence_is_a_fact_linked_to_the_races_it_names(self):
        _seed()
        races = _races()
        with connect() as conn:
            rows = [wf._fact_dict(row) for row in conn.execute("SELECT * FROM world_facts WHERE kind = 'magic'")]
        rule = next(row for row in rows if row["text"].startswith("Only elves"))
        self.assertEqual(set(rule["links"]), {races["elf"]["code"], races["spirit-touched"]["code"]})

    def test_custom_style_becomes_short_facts(self):
        _seed()
        with connect() as conn:
            rows = [dict(row) for row in conn.execute("SELECT kind, title, text FROM world_facts")]
        self.assertTrue(all(len(row["text"]) <= wf.TEXT_MAX for row in rows))
        kinds = {row["kind"] for row in rows}
        self.assertIn("tone", kinds)
        self.assertIn("faction", kinds)
        self.assertTrue(any("harsh climates" in row["text"] for row in rows))

    def test_known_people_numbers_and_rolled_numbers_are_stable(self):
        _seed()
        first = _races()
        self.assertEqual(first["elf"]["lifespan_years"], 700)
        _seed()
        second = _races()
        self.assertEqual(first["beastfolk"]["lifespan_years"], second["beastfolk"]["lifespan_years"])
        self.assertIn(second["beastfolk"]["size_band"], wf.SIZE_BANDS)

    def test_ability_rules_attach_to_their_people(self):
        _seed({**LOGGED_OPTIONS, "race_ability_rules": "Dwarves: sense stone through their boots; orcs heal fast after rest."})
        races = _races()
        self.assertIn("sense stone", races["dwarf"]["ability_rules"])
        self.assertIn("heal fast", races["orc"]["ability_rules"])
        self.assertEqual(races["elf"]["ability_rules"], "")

    def test_split_helpers(self):
        self.assertEqual(wf.split_list("human, Elf and dwarf; elf"), ["human", "Elf", "dwarf"])
        long = "word " * 80
        self.assertTrue(all(len(piece) <= wf.TEXT_MAX for piece in wf.split_sentences(long)))


class ValidationTest(unittest.TestCase):
    def test_bad_race_rows_are_refused(self):
        self.assertIsNone(wf.validate_race_row({"name": "elf", "magic_access": "sometimes"})[0])
        self.assertIsNone(wf.validate_race_row({"name": "a people with a very long descriptive name"})[0])
        self.assertIsNone(wf.validate_race_row({"name": "elf", "lifespan_years": -4})[0])
        self.assertIsNone(wf.validate_race_row({"name": "elf", "traits": "x" * 200})[0])
        self.assertIsNotNone(wf.validate_race_row({"name": "elf", "magic_access": "Innate"})[0])

    def test_bad_fact_rows_are_refused(self):
        codes = {"R1", "F1"}
        good = {"kind": "custom", "title": "Market day", "text": "Trade happens once a week at the gate.", "links": ["R1"]}
        self.assertIsNotNone(wf.validate_fact_row(good, codes)[0])
        self.assertIsNone(wf.validate_fact_row({**good, "kind": "gossip"}, codes)[0])
        self.assertIsNone(wf.validate_fact_row({**good, "text": "x" * 260}, codes)[0])
        self.assertIsNone(wf.validate_fact_row({**good, "links": ["R9"]}, codes)[0])
        self.assertIsNone(wf.validate_fact_row({**good, "title": ""}, codes)[0])

    def test_model_lines_are_validated_by_the_engine(self):
        _seed()
        races = _races()
        elf, human = races["elf"]["code"], races["human"]["code"]
        content = "\n".join(
            [
                f"RACE|{human}|none|75|medium|hardy, stubborn|",
                f"RACE|{elf}|sometimes|700|medium||",  # bad enum
                "RACE|R99|innate|10|small||",  # not in the table
                f"FACT|custom|Gate tolls|Travellers pay a toll in goods at every settlement gate.|{human}|trade toll",
                "FACT|gossip|Bad kind|This kind is not one of the allowed kinds at all.||",
                "FACT|history|Bad link|An old war emptied the northern valleys long ago.|F999|",
                "some prose the model added",
            ]
        )
        with connect() as conn:
            report = wf.apply_refinement(conn, content)
        self.assertEqual(report["accepted"], {"races": 1, "facts": 1})
        self.assertEqual(len(report["rejected"]), 4)
        races = _races()
        self.assertEqual(races["human"]["traits"], "hardy, stubborn")
        self.assertEqual(races["human"]["source"], "model")
        self.assertEqual(races["elf"]["magic_access"], "innate")

    def test_qwen3_8b_reply_shape(self):
        """The isolated 8B probe's reply: one-letter codes, restated setup sentences, every race linked."""
        _seed()
        content = "\n".join(
            [
                "RACE|H|none|80|medium||",
                "RACE|elf|innate|700|medium|long memories|",
                "RACE|spirit-touched|innate|400|medium||",
                "FACT|magic|Only elves and Spirit touched spirits|magic is restricted to elves and spirit-touched individuals|R1 R2 R3 R4 R5 R6",
                "FACT|tone|The mood is grounded and adventurous|local stakes and fair challenges|",
                "FACT|custom|Winter roads|Snow closes the high passes for three months and settlements stockpile grain.||",
            ]
        )
        with connect() as conn:
            report = wf.apply_refinement(conn, content)
            stored = [wf._fact_dict(row) for row in conn.execute("SELECT * FROM world_facts WHERE source = 'model'")]
        self.assertEqual(report["accepted"]["races"], 2)
        self.assertTrue(any("RACE H" in line for line in report["rejected"]))
        races = _races()
        self.assertEqual(races["spirit-touched"]["lifespan_years"], 400)
        self.assertEqual(races["elf"]["traits"], "long memories")
        texts = [row["text"] for row in stored]
        self.assertIn("Snow closes the high passes for three months and settlements stockpile grain.", texts)
        self.assertFalse(any("local stakes" in text for text in texts))
        restricted = [row for row in stored if row["text"].startswith("magic is restricted")]
        if restricted:  # kept only with the two peoples it names
            self.assertEqual(set(restricted[0]["links"]), {races["elf"]["code"], races["spirit-touched"]["code"]})


class RelevanceTest(unittest.TestCase):
    def test_present_npc_race_comes_first_with_the_rule_that_names_it(self):
        _seed()
        with connect() as conn:
            out = wf.relevant_facts(
                conn,
                present=[{"name": "Aria", "race": "human"}, {"name": "Lirien", "race": "elf"}],
                text="can you teach me magic?",
                location_name="The Back Lane",
            )
        names = [row["name"] for row in out["races"]]
        self.assertEqual(names[:2], ["human", "elf"])
        self.assertEqual(out["races"][0]["here"], ["Aria"])
        self.assertEqual(out["races"][0]["magic"], "none")
        self.assertTrue(any(fact["text"].startswith("Only elves") for fact in out["facts"]))
        self.assertNotIn("dwarf", names)

    def test_named_race_is_fetched_and_budget_holds(self):
        _seed()
        with connect() as conn:
            out = wf.relevant_facts(conn, present=[], text="I ask about the dwarves in the hills")
            small = wf.relevant_facts(conn, present=[{"name": "Aria", "race": "human"}], text="magic", budget_chars=120)
        self.assertEqual([row["name"] for row in out["races"]], ["dwarf"])
        self.assertLessEqual(len(json.dumps(small, separators=(",", ":"))), 120 + 40)

    def test_old_world_without_rows_is_seeded_on_first_read(self):
        with connect() as conn:
            wf.clear_world_facts(conn)
            conn.execute(
                "INSERT INTO settings (key, value) VALUES ('playthrough_options', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (json.dumps(LOGGED_OPTIONS),),
            )
        state = {
            "current_location": {"code": "L1", "name": "The Back Lane"},
            "locations": [{"code": "L1", "npcs": [{"name": "Aria", "race": "human"}]}],
        }
        out = wf.relevant_facts_for_state(state, "hello")
        self.assertEqual(out["races"][0]["name"], "human")


class PlaythroughTest(unittest.TestCase):
    def test_start_seeds_rows_and_the_draft_packet_carries_them(self):
        world.start_playthrough({**LOGGED_OPTIONS, "player_name": "Harrow Ames", "special_ability_origin": "none"})
        races = _races()
        self.assertEqual(races["human"]["magic_access"], "none")
        with connect() as conn:
            loc = conn.execute("SELECT id FROM locations ORDER BY id LIMIT 1").fetchone()
            conn.execute("UPDATE player SET current_location_id = ?", (loc["id"],))
            conn.execute(
                "INSERT INTO npcs (code, location_id, name, race, role) VALUES ('ZZ', ?, 'Aria', 'human', 'baker')",
                (loc["id"],),
            )
        from app.llm import _clean_context_for_handoff
        from app.turn_dsl import build_dsl_user_prompt

        state = world.get_state()
        context = world.build_prompt_context(state, "Aria, can you teach me magic?")
        self.assertEqual(context["world_facts"]["races"][0]["here"], ["Aria"])
        cleaned = _clean_context_for_handoff(context, "test")
        packet = json.loads(build_dsl_user_prompt(cleaned, "Aria, can you teach me magic?"))
        facts = packet["world_state"]["world_facts"]
        self.assertEqual(facts["races"][0]["name"], "human")
        self.assertEqual(facts["races"][0]["magic"], "none")
        self.assertIn("world_facts", packet["instruction"])

    def test_post_start_pass_off_leaves_the_split(self):
        world.start_playthrough({**LOGGED_OPTIONS, "player_name": "Harrow Ames", "special_ability_origin": "none"})
        report = wf.run_post_start_passes()
        self.assertFalse(report["model_allowed"])
        self.assertFalse(report["passes"]["world_facts"]["called"])
        with connect() as conn:
            stored = wf.all_facts(conn)
        self.assertEqual(len(stored["races"]), 6)
        self.assertFalse(stored["post_start_pass"]["model_allowed"])

    def test_world_facts_route_is_registered_and_reads(self):
        from app import main

        paths = {getattr(route, "path", "") for route in main.app.routes}
        self.assertIn("/api/world-facts", paths)
        _seed()
        out = main.api_world_facts()
        self.assertEqual(len(out["races"]), 6)
        self.assertTrue(out["facts"])


if __name__ == "__main__":
    unittest.main()
