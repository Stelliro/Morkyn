"""
Playtest #23: world facts were thin in the game-2 save (auto-ab564b3c-t00004).

The save held six races (R1-R6) with magic access and nothing else: no
traits, no ability rules. The post-start pass proposed four facts and all four
were refused as restating stored ones, because it was shown the setup text
and asked for facts "the table does not hold yet". What was left were setup
sentences chopped up, titled by their first six words ("In a land of
mist-shrouded forests") and tagged with words like "both", plus two
near-empty rows ("Faction pressure in this world: local disputes."). The
player had no race stored at all.

These tests use the save's strings (copied, read-only) and check:
  - every race row has engine-rolled traits with no model;
  - titles are subject noun phrases and tags are nouns;
  - faction_pressure is one setting row, replaced when the pass names factions;
  - a marker-only world_races list resolves to a real list;
  - the player's race is stored, exposed in the API and the turn packet;
  - the pass asks for new facts with the stored ones as already known,
    with a fresh draw of fact kinds per call, and keeps rule-decided magic.
"""
from __future__ import annotations

import json
import os
import random
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-world-facts-enrich-"))
os.environ.update(isolated_data_env(str(_TMP)))
os.environ.update(
    {
        "AI_RPG_PACK_DIR": str(_TMP / "packs"),
        "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
        "AI_RPG_POST_START_MODEL": "off",
    }
)

from app import db, world  # noqa: E402
from app import example_pools as ep  # noqa: E402
from app import world_facts as wf  # noqa: E402
from app.db import connect  # noqa: E402

# The game-2 save's playthrough_options, the fields this module reads.
GAME2 = {
    "world_style": "frontier dark fantasy",
    "custom_style": (
        "In a land of mist-shrouded forests and storm-wracked coasts, the kingdom of Eldoria is ruled by a council "
        "of mages and warrior-princes. Magic and technology coexist, with arcane arts dictating the fates of commoners "
        "and nobles alike. Power is earned through both combat prowess and magical aptitude, and the air is thick with "
        "the tension of high stakes and unwritten codes of honor."
    ),
    "magic_level": "rare",
    "tech_level": "medieval",
    "tone": "tense and honorable",
    "world_races": "human, elf, dwarf, orc, beastfolk, spirit-touched",
    "race_magic_enabled": True,
    "race_magic_rarity": "common for specific races",
    "race_magic_rules": "Only elves and Spirit touched/spirits have magic.",
    "race_ability_rules": "",
    "faction_pressure": "local disputes, hidden cults",
    "character_backstory": (
        "Miriam Shaw, a stagehand with a knack for rigging and a passion for storytelling, was transported to the new "
        "world after a mysterious ferry accident."
    ),
}

# The rejected reply shape from the save's world_facts_pass, plus new lore.
MODEL_REPLY = "\n".join(
    [
        "RACE|human|innate|80|medium|short-lived, stubborn, spread across every trade|learn any craft by practice",
        "RACE|elf|innate|700|medium|tall, slow to trust, keepers of old songs|sense spirits nearby; cast through song",
        "RACE|dwarf|none|300|small|stocky clan folk who keep oaths|see in the dark; resist poison",
        "FACT|custom|Kingdom of Eldoria|In a land of mist-shrouded forests, the kingdom of Eldoria is ruled by a council of mages.||",
        "FACT|faction|The Pale Lantern|The Pale Lantern is a hidden cult that buys forbidden relics and wants the council's mages gone.||cult relics",
        "FACT|custom|Oath of the threshold|Guests swear on salt at the door before they may eat under a host's roof.||oath salt guests",
    ]
)


def setUpModule():
    os.environ.update(isolated_data_env(str(_TMP)))
    assert str(db.db_path()).startswith(str(_TMP)), db.db_path()
    db.init_db()


def _seed(options=None):
    with connect() as conn:
        return wf.seed_from_options(conn, dict(options or GAME2))


def _races():
    with connect() as conn:
        return {row["name"]: dict(row) for row in conn.execute("SELECT * FROM world_races").fetchall()}


def _facts():
    with connect() as conn:
        return [wf._fact_dict(row) for row in conn.execute("SELECT * FROM world_facts ORDER BY id").fetchall()]


class SplitQualityTest(unittest.TestCase):
    def test_every_race_has_engine_traits_without_a_model(self):
        _seed()
        races = _races()
        self.assertEqual(len(races), 6)
        for name, row in races.items():
            self.assertTrue(row["traits"], name)
            self.assertLessEqual(len(row["traits"]), wf.TRAITS_MAX)
        first = {name: row["traits"] for name, row in races.items()}
        _seed()
        self.assertEqual(first, {name: row["traits"] for name, row in _races().items()}, "same world, same traits")

    def test_titles_are_subject_phrases_not_first_words(self):
        _seed()
        titles = {fact["text"][:30]: fact["title"] for fact in _facts()}
        self.assertIn("Kingdom of Eldoria", titles.values())
        self.assertIn("Magic and technology", titles.values())
        self.assertIn("Power through combat prowess", titles.values())
        self.assertNotIn("In a land of mist-shrouded forests", titles.values())
        for title in titles.values():
            self.assertLessEqual(len(title.split()), 8, title)

    def test_tags_are_nouns(self):
        _seed()
        tags = [tag for fact in _facts() for tag in fact["tags"]]
        for word in ("both", "touched", "mist-shrouded", "storm-wracked", "magical", "alike"):
            self.assertNotIn(word, tags)
        power = next(fact for fact in _facts() if fact["text"].startswith("Power is earned"))
        self.assertEqual(power["tags"][:3], ["power", "combat", "prowess"])

    def test_faction_pressure_is_one_setting_row(self):
        _seed()
        factions = [fact for fact in _facts() if fact["kind"] == "faction"]
        self.assertEqual(len(factions), 1)
        self.assertIn("local disputes", factions[0]["text"])
        self.assertIn("hidden cults", factions[0]["text"])
        self.assertNotIn("Faction pressure in this world", factions[0]["text"])

    def test_title_helper_shapes(self):
        self.assertEqual(wf._title_for("Only elves and Spirit touched/spirits have magic."), "Magic of elves and Spirit touched and spirits")
        self.assertEqual(wf._title_for("Magic is rare but present, shaping daily life."), "Rare magic")


class RaceListAndPlayerTest(unittest.TestCase):
    def test_marker_only_race_list_resolves(self):
        report = _seed({**GAME2, "world_races": "custom"})
        self.assertEqual(set(_races()), {"human"})
        self.assertEqual(report["player_race"], "human")
        report = _seed({**GAME2, "world_races": "human, custom, elf"})
        self.assertEqual(set(_races()), {"human", "elf"})

    def test_player_race_from_backstory_or_human(self):
        races = ["human", "elf", "dwarf"]
        self.assertEqual(wf.resolve_player_race(GAME2, races), "human")
        self.assertEqual(wf.resolve_player_race({"character_backstory": "She was reborn as an elf in the north."}, races), "elf")
        self.assertEqual(wf.resolve_player_race({"player_race": "Dwarves"}, races), "dwarf")
        self.assertEqual(wf.resolve_player_race({}, ["elf", "orc"]), "elf")
        # Naming another people is not being one.
        self.assertEqual(wf.resolve_player_race({"character_backstory": "Raised by elves after the war."}, races), "human")

    def test_start_stores_player_race_and_the_packet_carries_it(self):
        world.start_playthrough({**GAME2, "player_name": "Harrow Ames", "special_ability_origin": "none"})
        with connect() as conn:
            self.assertEqual(wf.player_race(conn), "human")
            loc = conn.execute("SELECT id FROM locations ORDER BY id LIMIT 1").fetchone()
            conn.execute("UPDATE player SET current_location_id = ?", (loc["id"],))
        state = world.get_state()
        self.assertEqual(state["player"]["race"], "human")
        context = world.build_prompt_context(state, "I look around.")
        human = next(row for row in context["world_facts"]["races"] if row["name"] == "human")
        self.assertTrue(human["player"])
        self.assertNotIn("Harrow Ames", human.get("here") or [])
        from app import main

        self.assertEqual(main.api_world_facts()["player_race"], "human")
        from app.prompts import _player_view

        self.assertEqual(_player_view({"player": state["player"]})["race"], "human")


class EnrichPassTest(unittest.TestCase):
    def test_request_shows_stored_facts_as_known_and_draws_asks(self):
        _seed()
        with connect() as conn:
            user_a, plan_a = wf.build_refine_request(conn, GAME2, random.Random(1))
            user_b, plan_b = wf.build_refine_request(conn, GAME2, random.Random(2))
        packet = json.loads(user_a)
        self.assertNotIn("custom_style", packet["setup"])
        self.assertTrue(any("kingdom of Eldoria" in line for line in packet["already_known"]))
        self.assertTrue(3 <= len(packet["write_facts_about"]) <= 5)
        self.assertTrue(any(ask.startswith("faction:") for ask in packet["write_facts_about"]))
        self.assertNotEqual(plan_a["asked"], plan_b["asked"])
        elf = next(row for row in packet["races"] if row["name"] == "elf")
        self.assertTrue(elf["magic_fixed"])
        self.assertNotIn("Restate", wf._REFINE_SYSTEM)
        self.assertIn("already_known", wf._REFINE_SYSTEM)

    def test_ask_pool_is_large_and_filtered(self):
        ctx = ep.world_context(GAME2)
        pool = ep._pool("world_fact_ask", ctx)
        self.assertGreaterEqual(len(pool), 15)
        no_magic = ep._pool("world_fact_ask", {**ctx, "magic": "none"})
        self.assertFalse(any(ask.startswith("magic:") for ask in no_magic))

    def test_reply_enriches_races_keeps_rule_magic_and_replaces_split_factions(self):
        _seed()
        with connect() as conn:
            report = wf.apply_refinement(conn, MODEL_REPLY, fixed_magic=wf._fixed_magic(
                [dict(row) for row in conn.execute("SELECT * FROM world_races")], GAME2))
        races = _races()
        self.assertEqual(races["human"]["magic_access"], "none", "the setup rule decides, not the model")
        self.assertTrue(any("human" in line or "R1" in line for line in report.get("adjusted", [])))
        self.assertIn("see in the dark", races["dwarf"]["ability_rules"])
        self.assertIn("slow to trust", races["elf"]["traits"])
        self.assertEqual(report["accepted"]["facts"], 2)
        self.assertTrue(any("restates" in line for line in report["rejected"]))
        factions = [fact for fact in _facts() if fact["kind"] == "faction"]
        self.assertEqual([fact["title"] for fact in factions], ["The Pale Lantern"])
        self.assertTrue(report["replaced_split_factions"])
        oath = next(fact for fact in _facts() if fact["title"] == "Oath of the threshold")
        self.assertIn("oath", oath["tags"])

    def test_codes_written_into_the_text_become_links(self):
        """The isolated 8B probe on game 2's options ended each fact with all six race codes."""
        _seed()
        line = ("FACT|custom|Daily Sustenance|Ordinary people trade dried meat and salted fish, and elves trade "
                "herbs. R1 R2 R3 R4 R5 R6|")
        with connect() as conn:
            wf.apply_refinement(conn, line, fixed_magic={})
        fact = next(fact for fact in _facts() if fact["title"] == "Daily Sustenance")
        self.assertTrue(fact["text"].endswith("herbs."))
        self.assertEqual(fact["links"], [_races()["elf"]["code"]])
        for word in ("ordinary", "dried", "salted"):
            self.assertNotIn(word, fact["tags"])

    def test_no_faction_from_model_keeps_the_setting_row(self):
        _seed()
        with connect() as conn:
            wf.apply_refinement(conn, "FACT|custom|Salt oath|Guests swear on salt at the door before they eat.||", fixed_magic={})
        self.assertEqual(len([fact for fact in _facts() if fact["kind"] == "faction"]), 1)


if __name__ == "__main__":
    unittest.main()
