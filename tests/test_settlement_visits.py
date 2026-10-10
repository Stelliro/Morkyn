"""Tests for app/settlement_visits.py (TODO g8, built but not wired).

The module is a leaf: nothing in app/ or static/ imports it. These tests run it against a
temporary database with no model, no network and no wall clock.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-settlement-visits-test-"))
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
}
os.environ.update(_ENV)

from app.db import connect, db_path, init_db  # noqa: E402
from app import settlement_visits as sv  # noqa: E402

MODULE_PATH = ROOT / "app" / "settlement_visits.py"


def setUpModule():
    os.environ.update(_ENV)
    init_db()
    with connect() as conn:
        sv.ensure_schema(conn)


def _world_time(day: int, minute: int, label: str = "") -> dict:
    return {"day": day, "minute": minute, "label": label}


def _table_counts(conn) -> dict[str, int]:
    names = [
        r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    ]
    counts = {}
    for name in names:
        counts[name] = int(conn.execute(f'SELECT COUNT(*) AS n FROM "{name}"').fetchone()["n"])
    return counts


class LeafTests(unittest.TestCase):
    def test_module_is_a_leaf(self):
        pattern = re.compile(r"app\.settlement_visits|import settlement_visits")
        offenders = []
        for folder in ("app", "static"):
            for path in (ROOT / folder).rglob("*"):
                if not path.is_file() or path.suffix not in {".py", ".js", ".html", ".css"}:
                    continue
                if path == MODULE_PATH:
                    continue
                try:
                    text = path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                if pattern.search(text):
                    offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual(offenders, [], f"settlement_visits is imported by: {offenders}")
        doc = sv.__doc__ or ""
        self.assertIn("Status: built, not wired (TODO g8).", doc)
        self.assertIn("Wiring (not done):", doc)
        self.assertIn("Turn on:", doc)
        self.assertIn("Tests: tests/test_settlement_visits.py", doc)

    def test_docstring_hooks_name_real_functions(self):
        hooks = {
            "app/world.py": ["def apply_map_travel_step(", "def build_ambient_move_line(", "def get_state(",
                             "def _turn_value(", "def ensure_settlement_ruler(", "def _spend_travel("],
            "app/town_moves.py": ["def enter_town(", "def settlement_row("],
            "app/db.py": ["def _migrate_columns("],
            "app/turn_prompts.py": ["def state_view("],
        }
        for rel, names in hooks.items():
            text = (ROOT / rel).read_text(encoding="utf-8")
            for name in names:
                self.assertIn(name, text, f"{rel} no longer defines {name}")
        world_text = (ROOT / "app" / "world.py").read_text(encoding="utf-8")
        for name in ("WORLD_TABLES", "RESTORE_ORDER", "_REPLACE_ONLY_WHEN_EXPORTED", "def _save_snapshot(",
                     "def _restore_snapshot_rows(", "def _clear_playthrough(", "You enter the bounds of"):
            self.assertIn(name, world_text)


class PureTests(unittest.TestCase):
    def test_settlement_key_from_meta_city_and_string(self):
        self.assertEqual(sv.settlement_key({"id": "S3"}), "S3")
        self.assertEqual(sv.settlement_key({"id": "C7", "band": "town"}), "C7")
        self.assertEqual(sv.settlement_key("S9"), "S9")
        self.assertEqual(sv.settlement_key(" S9 "), "S9")
        self.assertEqual(sv.settlement_key({}), "")
        self.assertEqual(sv.settlement_key(None), "")
        self.assertEqual(sv.settlement_key({"settlement_id": "S4"}), "S4")
        self.assertEqual(sv.settlement_key({"city_id": "C2"}), "C2")

    def test_settlement_class_mapping(self):
        for word, expected in sv.SETTLEMENT_CLASS.items():
            self.assertEqual(sv.settlement_class({"state": word}), expected, word)
            self.assertEqual(sv.settlement_class({"class": word}), expected, word)
            self.assertEqual(sv.settlement_class({"band": word}), expected, word)
        self.assertEqual(sv.settlement_class({"state": "Large_City"}), "city")
        self.assertEqual(sv.settlement_class({"state": "ruins"}), "town")
        self.assertEqual(sv.settlement_class({}), "town")
        self.assertEqual(sv.settlement_class(None), "town")
        self.assertEqual(sv.settlement_class({"state": "", "band": "hamlet"}), "village")

    def test_settlement_name_fallbacks(self):
        self.assertEqual(sv.settlement_name({"name": "Ashbarrow"}), "Ashbarrow")
        self.assertEqual(sv.settlement_name({"label": "The Quay", "state": "harbor"}), "The Quay")
        self.assertEqual(sv.settlement_name({"state": "harbor"}), "Harbor")
        self.assertEqual(sv.settlement_name(None), "Town")

    def test_rules_tables_match_the_seeder(self):
        self.assertEqual(sv.REENTRY_GRACE_MINUTES, 30)
        self.assertEqual((sv.POWER_MIN, sv.POWER_MAX, sv.POWER_DEFAULT), (30, 100, 50))
        self.assertEqual((sv.OFFICER_COUNT, sv.WORKER_COUNT), (2, 2))
        self.assertEqual(sv.POWER_BY_BAND, {"hamlet": 35, "village": 42, "town": 50, "city": 62,
                                            "large_city": 72, "metropolis": 85})
        from app import world
        self.assertEqual(sv.RULER_ROLES, world._RULER_ROLE_BY_CLASS)
        self.assertEqual(sv.RULER_ROLE_DEFAULT, "local authority")
        self.assertEqual(sv.officer_power(57, 0), 37)
        self.assertEqual(sv.officer_power(57, 1), 32)
        self.assertEqual(sv.worker_power(57, 0), 14)
        self.assertEqual(sv.worker_power(57, 1), 12)
        self.assertEqual(sv.officer_power(30, 1), 15)
        self.assertEqual(sv.worker_power(30, 1), 5)

    def test_is_entry_step_rule(self):
        self.assertTrue(sv.is_entry_step({"settlement_id": "S3", "from_terrain": "forest"}))
        self.assertFalse(sv.is_entry_step({"settlement_id": "S3", "from_terrain": "town"}))
        self.assertFalse(sv.is_entry_step({"settlement_id": "S3", "from_terrain": "harbor"}))
        self.assertFalse(sv.is_entry_step({"from_terrain": "forest"}))
        self.assertFalse(sv.is_entry_step({"settlement_id": "", "from_terrain": "forest"}))
        self.assertFalse(sv.is_entry_step(None))
        self.assertTrue(sv.is_entry_step({"settlement_id": "S3", "from_terrain": ""}))
        # ruins, dungeon and gate are map states, not settlements: a step from one onto a town is an entry.
        for word in ("ruins", "dungeon", "gate"):
            self.assertTrue(sv.is_entry_step({"settlement_id": "S3", "from_terrain": word}), word)
        self.assertEqual(sv.SETTLEMENT_TERRAINS,
                         {"city", "town", "village", "station", "colony", "harbor", "shipyard"})
        from app.tile_world import SETTLEMENT_STATES
        self.assertEqual(sv.SETTLEMENT_TERRAINS | sv.NOT_SETTLEMENTS, set(SETTLEMENT_STATES))

    def test_seed_proposal_pure(self):
        seed = sv.seed_proposal({"id": "S3", "state": "town", "ruler_power_rank": 57}, location_id=5)
        self.assertEqual(seed["settlement_id"], "S3")
        self.assertEqual(seed["location_id"], 5)
        self.assertEqual(seed["class"], "town")
        self.assertEqual(seed["flag_key"], "settlement_ruler:S3")
        self.assertEqual(seed["power_source"], "meta")
        self.assertEqual(seed["ruler"], {"role": "town head", "power_rank": 57, "presence": "full",
                                         "tier": "ruler", "shell": 0})
        self.assertEqual([o["role"] for o in seed["officers"]], ["constable", "market warden"])
        self.assertEqual([o["power_rank"] for o in seed["officers"]], [37, 32])
        self.assertEqual([w["role"] for w in seed["workers"]], ["carter", "apprentice"])
        self.assertEqual([w["power_rank"] for w in seed["workers"]], [14, 12])
        for o in seed["officers"]:
            self.assertEqual((o["presence"], o["tier"], o["shell"]), ("event_worthy", "staff", 0))
        for w in seed["workers"]:
            self.assertEqual((w["presence"], w["tier"], w["shell"]), ("background", "staff", 1))
        self.assertTrue(seed["apply"].startswith("app.world.ensure_settlement_ruler(conn, location_id=5, settlement="))
        self.assertIsNone(sv.seed_proposal({"id": "S3"}, location_id=5, ruler_exists=True))
        self.assertIsNone(sv.seed_proposal({"id": "S3"}, location_id=0))
        self.assertIsNone(sv.seed_proposal({}, location_id=5))
        self.assertIsNone(sv.seed_proposal(None, location_id=5))

    def test_seed_default_roles_for_unlisted_class(self):
        seed = sv.seed_proposal({"id": "S1", "state": "farm"}, location_id=2)
        self.assertEqual(seed["class"], "farm")
        self.assertEqual(seed["ruler"]["role"], "landholder")
        self.assertEqual([o["role"] for o in seed["officers"]], ["deputy", "scribe"])
        self.assertEqual([w["role"] for w in seed["workers"]], ["laborer", "helper"])

    def test_power_clamp_and_band_fallback(self):
        low = sv.seed_proposal({"id": "S1", "state": "town", "ruler_power_rank": 7}, location_id=1)
        self.assertEqual(low["ruler"]["power_rank"], 30)
        self.assertEqual(low["power_source"], "meta")
        high = sv.seed_proposal({"id": "S1", "state": "town", "ruler_power_rank": 140}, location_id=1)
        self.assertEqual(high["ruler"]["power_rank"], 100)
        band = sv.seed_proposal({"id": "C7", "band": "large_city"}, location_id=1)
        self.assertEqual(band["ruler"]["power_rank"], 72)
        self.assertEqual(band["power_source"], "band")
        self.assertEqual(band["class"], "city")
        self.assertEqual(band["ruler"]["role"], "city reeve")
        # The apply line's record must resolve to the same class under the seeder, which reads state or class.
        import json
        applied = json.loads(band["apply"].split("settlement=", 1)[1].rstrip(")"))
        self.assertEqual(applied.get("state") or applied.get("class"), "city")
        self.assertEqual(applied["band"], "large_city")
        kept = json.loads(sv.seed_proposal({"id": "S1", "state": "harbor"}, location_id=1)["apply"]
                          .split("settlement=", 1)[1].rstrip(")"))
        self.assertEqual(kept["state"], "harbor")
        self.assertNotIn("class", kept)
        plain = sv.seed_proposal({"id": "C8"}, location_id=1)
        self.assertEqual(plain["ruler"]["power_rank"], 50)
        self.assertEqual(plain["power_source"], "default")
        self.assertEqual([o["power_rank"] for o in plain["officers"]], [30, 25])
        self.assertEqual([w["power_rank"] for w in plain["workers"]], [12, 10])

    def test_journal_line_wording(self):
        first = sv.journal_line({"id": "S3", "name": "Ashbarrow", "state": "town"}, first_visit=True, visit_count=1,
                                world_time=_world_time(2, 90, "Day 2, 01:30"))
        self.assertEqual(first, "First visit to Ashbarrow (town). Day 2, 01:30.")
        again = sv.journal_line({"id": "S3", "name": "Ashbarrow"}, first_visit=False, visit_count=3, turn=12)
        self.assertEqual(again, "Back in Ashbarrow (visit 3). Turn 12.")
        self.assertLessEqual(len(sv.journal_line({"name": "x" * 2000}, first_visit=True, visit_count=1)), 900)

    def test_settlement_ref_is_economy_profile(self):
        from app import economy
        record = {"id": "C7", "band": "large_city", "name": "X"}
        ref = sv.settlement_ref(record, location_id=5)
        self.assertEqual(ref, economy.settlement_profile(record, {"id": 5}))
        self.assertEqual(sv.settlement_ref(record), economy.settlement_profile(record, None))
        for key, kind in (("settlement_id", str), ("name", str), ("size", str), ("type", str), ("band_raw", str),
                          ("population_band", str), ("population_factor", float), ("location_id", int)):
            self.assertIn(key, ref)
            self.assertIsInstance(ref[key], kind, key)
        self.assertEqual(ref["settlement_id"], "C7")
        self.assertEqual(ref["location_id"], 5)
        self.assertEqual(ref["size"], "city")
        self.assertIn(ref["population_band"], ("tiny", "small", "medium", "large"))
        for value in sv.SETTLEMENT_CLASS.values():
            self.assertIn(value, economy.SETTLEMENT_TYPES, value)


class SettlementVisitsDbTests(unittest.TestCase):
    def setUp(self):
        os.environ.update(_ENV)
        path = db_path()
        if path.exists():
            path.unlink()
        init_db()
        with connect() as conn:
            sv.ensure_schema(conn)
            # init_db seeds a player row; replace it with the template row so every test starts alike.
            conn.execute(
                "INSERT OR REPLACE INTO player (id, name, health, max_health, level, xp, gold, current_location_id) "
                "VALUES (1, 'T', 20, 20, 1, 0, 12, NULL)"
            )

    def test_ensure_schema_idempotent(self):
        with connect() as conn:
            sv.ensure_schema(conn)
            sv.ensure_schema(conn)
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'settlement_visits'"
            ).fetchone()
            self.assertIsNotNone(row)
            columns = {r["name"] for r in conn.execute("PRAGMA table_info(settlement_visits)").fetchall()}
        self.assertEqual(columns, {
            "settlement_id", "map_id", "name", "class", "location_id", "x", "y", "first_visit_turn",
            "first_visit_minute", "last_visit_turn", "last_visit_minute", "visit_count", "created_at",
        })

    def test_first_visit_creates_row_and_seed(self):
        with connect() as conn:
            self.assertTrue(sv.is_first_visit(conn, "S3"))
            result = sv.record_enter(
                conn, "S3", 4, settlement={"id": "S3", "state": "town", "ruler_power_rank": 57, "name": "Ashbarrow"},
                location_id=5, world_time=_world_time(1, 600, "Day 1, 10:00"),
            )
            self.assertFalse(sv.is_first_visit(conn, "S3"))
        self.assertTrue(result["first_visit"])
        self.assertTrue(result["counted"])
        self.assertFalse(result["ruler_exists"])
        row = result["visit"]
        self.assertEqual(row["settlement_id"], "S3")
        self.assertEqual(row["visit_count"], 1)
        self.assertEqual(row["first_visit_turn"], 4)
        self.assertEqual(row["last_visit_turn"], 4)
        self.assertEqual(row["first_visit_minute"], 600)
        self.assertEqual(row["last_visit_minute"], 600)
        self.assertEqual(row["location_id"], 5)
        self.assertEqual(row["name"], "Ashbarrow")
        self.assertEqual(row["class"], "town")
        seed = result["seed"]
        self.assertEqual(seed["ruler"]["power_rank"], 57)
        self.assertEqual([o["power_rank"] for o in seed["officers"]], [37, 32])
        self.assertEqual([w["power_rank"] for w in seed["workers"]], [14, 12])
        self.assertEqual(seed["flag_key"], "settlement_ruler:S3")
        self.assertEqual(seed["location_id"], 5)
        self.assertTrue(result["journal"]["content"].startswith("First visit to Ashbarrow (town)."))
        self.assertIn("Day 1, 10:00", result["journal"]["content"])

    def test_enter_result_shape(self):
        with connect() as conn:
            result = sv.record_enter(conn, "S3", 1, settlement={"id": "S3", "state": "village"}, location_id=2)
        self.assertEqual(set(result.keys()),
                         {"settlement_id", "first_visit", "counted", "visit", "journal", "ruler_exists", "seed"})
        self.assertIsInstance(result["settlement_id"], str)
        self.assertIsInstance(result["first_visit"], bool)
        self.assertIsInstance(result["counted"], bool)
        self.assertIsInstance(result["visit"], dict)
        self.assertIsInstance(result["ruler_exists"], bool)
        seed = result["seed"]
        self.assertEqual(set(seed.keys()), {"settlement_id", "location_id", "class", "flag_key", "power_source",
                                            "ruler", "officers", "workers", "apply"})
        self.assertEqual(len(seed["officers"]), sv.OFFICER_COUNT)
        self.assertEqual(len(seed["workers"]), sv.WORKER_COUNT)
        for person in [seed["ruler"], *seed["officers"], *seed["workers"]]:
            self.assertEqual(set(person.keys()), {"role", "power_rank", "presence", "tier", "shell"})
            self.assertIsInstance(person["power_rank"], int)
        self.assertIsInstance(seed["apply"], str)

    def test_journal_is_a_journal_note(self):
        with connect() as conn:
            result = sv.record_enter(conn, "S3", 1, settlement={"id": "S3", "name": "Ashbarrow"}, location_id=2)
        note = result["journal"]
        self.assertEqual(set(note.keys()), {"kind", "content"})
        self.assertEqual(note["kind"], "visit")
        self.assertLessEqual(len(note["kind"]), 40)
        self.assertIsInstance(note["content"], str)
        self.assertLessEqual(len(note["content"]), 900)
        self.assertTrue(note["content"])

    def test_seed_none_when_ruler_flag_set(self):
        with connect() as conn:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                ("settlement_ruler:S3", '{"code": "A", "power_rank": 50}'),
            )
            self.assertTrue(sv.ruler_exists(conn, "S3"))
            self.assertFalse(sv.ruler_exists(conn, "S4"))
            self.assertFalse(sv.ruler_exists(conn, ""))
            result = sv.record_enter(conn, "S3", 4, settlement={"id": "S3", "state": "town"}, location_id=5)
        self.assertTrue(result["ruler_exists"])
        self.assertIsNone(result["seed"])
        self.assertTrue(result["first_visit"])
        self.assertIsNotNone(result["journal"])

    def test_ruler_flag_falsy_values(self):
        with connect() as conn:
            for value in ("", "0", "false", "null", "{}", "[]"):
                conn.execute(
                    "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    ("settlement_ruler:S3", value),
                )
                self.assertFalse(sv.ruler_exists(conn, "S3"), value)
            conn.execute("UPDATE settings SET value = ? WHERE key = ?", ("true", "settlement_ruler:S3"))
            self.assertTrue(sv.ruler_exists(conn, "S3"))

    def test_reentry_within_grace_not_counted(self):
        with connect() as conn:
            first = sv.record_enter(conn, "S3", 4, settlement={"id": "S3", "state": "town"}, location_id=5,
                                    world_time=_world_time(1, 600))
            second = sv.record_enter(conn, "S3", 4, settlement={"id": "S3", "state": "town"}, location_id=5,
                                     world_time=_world_time(1, 610))
        self.assertTrue(first["counted"])
        self.assertFalse(second["counted"])
        self.assertFalse(second["first_visit"])
        self.assertEqual(second["visit"]["visit_count"], 1)
        self.assertEqual(second["visit"]["last_visit_minute"], 600)
        self.assertIsNone(second["journal"])
        self.assertIsNotNone(second["seed"])  # still offered: a first visit whose seeding never ran
        self.assertEqual(second["seed"]["flag_key"], "settlement_ruler:S3")

    def test_reentry_after_grace_counts(self):
        with connect() as conn:
            sv.record_enter(conn, "S3", 4, settlement={"id": "S3", "state": "town", "name": "Ashbarrow"},
                            location_id=5, world_time=_world_time(1, 600))
            result = sv.record_enter(conn, "S3", 4, settlement={"id": "S3", "state": "town", "name": "Ashbarrow"},
                                     location_id=5, world_time=_world_time(1, 645, "Day 1, 10:45"))
        self.assertTrue(result["counted"])
        self.assertFalse(result["first_visit"])
        self.assertEqual(result["visit"]["visit_count"], 2)
        self.assertEqual(result["visit"]["last_visit_minute"], 645)
        self.assertEqual(result["visit"]["first_visit_minute"], 600)
        self.assertEqual(result["journal"]["content"], "Back in Ashbarrow (visit 2). Day 1, 10:45.")

    def test_reentry_on_a_later_turn_counts(self):
        with connect() as conn:
            sv.record_enter(conn, "S3", 4, settlement={"id": "S3"}, location_id=5, world_time=_world_time(1, 600))
            result = sv.record_enter(conn, "S3", 5, settlement={"id": "S3"}, location_id=5,
                                     world_time=_world_time(1, 605))
        self.assertTrue(result["counted"])
        self.assertEqual(result["visit"]["visit_count"], 2)
        self.assertEqual(result["visit"]["last_visit_turn"], 5)

    def test_day_boundary_uses_abs_minutes(self):
        # Raw minutes would read day 1 minute 10 to day 2 minute 15 as five minutes; absolute it is 1445.
        with connect() as conn:
            first = sv.record_enter(conn, "S3", 4, settlement={"id": "S3"}, location_id=5,
                                    world_time=_world_time(1, 10))
            result = sv.record_enter(conn, "S3", 4, settlement={"id": "S3"}, location_id=5,
                                     world_time=_world_time(2, 15))
        self.assertEqual(first["visit"]["first_visit_minute"], 10)
        self.assertTrue(result["counted"])
        self.assertEqual(result["visit"]["visit_count"], 2)
        self.assertEqual(result["visit"]["last_visit_minute"], 1455)
        # Across midnight within the grace: day 2 minute 1430 then day 3 minute 5 is 15 minutes, not counted.
        with connect() as conn:
            sv.record_enter(conn, "S4", 4, settlement={"id": "S4"}, location_id=5, world_time=_world_time(2, 1430))
            result = sv.record_enter(conn, "S4", 4, settlement={"id": "S4"}, location_id=5,
                                     world_time=_world_time(3, 5))
        self.assertFalse(result["counted"])
        self.assertEqual(result["visit"]["visit_count"], 1)
        self.assertEqual(result["visit"]["last_visit_minute"], 2870)

    def test_fields_fill_only_when_blank(self):
        with connect() as conn:
            first = sv.record_enter(conn, "S3", 1, settlement={"id": "S3"}, world_time=_world_time(1, 0))
            self.assertEqual(first["visit"]["name"], "")
            self.assertEqual(first["visit"]["location_id"], 0)
            self.assertEqual(first["visit"]["x"], 0)
            second = sv.record_enter(conn, "S3", 2, settlement={"id": "S3", "name": "Ashbarrow", "state": "harbor"},
                                     location_id=7, map_id="map-1", x=3, y=4, world_time=_world_time(1, 100))
            self.assertEqual(second["visit"]["name"], "Ashbarrow")
            self.assertEqual(second["visit"]["location_id"], 7)
            self.assertEqual(second["visit"]["map_id"], "map-1")
            self.assertEqual(second["visit"]["class"], "harbor")
            self.assertEqual((second["visit"]["x"], second["visit"]["y"]), (3, 4))
            third = sv.record_enter(conn, "S3", 3, settlement={"id": "S3", "name": "Other", "state": "city"},
                                    location_id=9, map_id="map-2", x=8, y=9, world_time=_world_time(1, 200))
        self.assertEqual(third["visit"]["name"], "Ashbarrow")
        self.assertEqual(third["visit"]["location_id"], 7)
        self.assertEqual(third["visit"]["map_id"], "map-1")
        self.assertEqual(third["visit"]["class"], "harbor")
        self.assertEqual((third["visit"]["x"], third["visit"]["y"]), (3, 4))
        self.assertEqual(third["visit"]["visit_count"], 3)

    def test_stored_town_class_gives_way_to_a_named_class(self):
        # "town" is also the default for a record with no class word, so a later class replaces it.
        with connect() as conn:
            first = sv.record_enter(conn, "S3", 1, settlement={"id": "S3", "state": "town"}, location_id=2)
            self.assertEqual(first["visit"]["class"], "town")
            second = sv.record_enter(conn, "S3", 2, settlement={"id": "S3", "state": "city"}, location_id=2,
                                     world_time=_world_time(1, 100))
            self.assertEqual(second["visit"]["class"], "city")
            self.assertEqual(second["seed"]["ruler"]["role"], "city reeve")
            third = sv.record_enter(conn, "S3", 3, settlement={"id": "S3", "state": "village"}, location_id=2,
                                    world_time=_world_time(1, 200))
        self.assertEqual(third["visit"]["class"], "city")

    def test_settlement_id_argument_wins_over_the_record_id(self):
        with connect() as conn:
            result = sv.record_enter(conn, "S3", 1, settlement={"id": "S4", "state": "town"}, location_id=2)
            self.assertIsNotNone(sv.get_visit(conn, "S3"))
            self.assertIsNone(sv.get_visit(conn, "S4"))
        self.assertEqual(result["settlement_id"], "S3")
        self.assertEqual(result["seed"]["settlement_id"], "S3")
        self.assertEqual(result["seed"]["flag_key"], "settlement_ruler:S3")
        self.assertIn('"id": "S3"', result["seed"]["apply"])

    def test_enter_from_travel_with_a_none_record_id(self):
        travel = {"settlement_id": "S5", "from_terrain": "forest", "to": [2, 2],
                  "settlement": {"id": None, "name": "Reedham"}}
        with connect() as conn:
            result = sv.enter_from_travel(conn, travel, location_id=3, turn=2)
        self.assertEqual(result["settlement_id"], "S5")
        self.assertEqual(result["visit"]["name"], "Reedham")
        self.assertEqual(result["seed"]["settlement_id"], "S5")

    def test_seed_uses_stored_location_when_call_has_none(self):
        with connect() as conn:
            sv.record_enter(conn, "S3", 1, settlement={"id": "S3", "state": "village", "name": "Reedham"}, location_id=7)
            later = sv.record_enter(conn, "S3", 2, world_time=_world_time(1, 300))
        self.assertIsNotNone(later["seed"])
        self.assertEqual(later["seed"]["location_id"], 7)
        self.assertEqual(later["seed"]["class"], "village")
        self.assertEqual(later["seed"]["ruler"]["role"], "village elder")
        self.assertTrue(later["journal"]["content"].startswith("Back in Reedham (visit 2)."))

    def test_blank_id_raises(self):
        with connect() as conn:
            with self.assertRaises(ValueError):
                sv.record_enter(conn, "", 1)
            with self.assertRaises(ValueError):
                sv.record_enter(conn, "   ", 1)
            with self.assertRaises(ValueError):
                sv.enter_from_city(conn, {"name": "Nowhere"}, location_id=1, turn=1, map_id="m")

    def test_turn_clamped_to_zero(self):
        with connect() as conn:
            result = sv.record_enter(conn, "S3", -4, settlement={"id": "S3"})
        self.assertEqual(result["visit"]["first_visit_turn"], 0)
        self.assertEqual(result["visit"]["last_visit_turn"], 0)
        self.assertEqual(result["visit"]["first_visit_minute"], 0)

    def test_enter_from_travel_none_off_settlement(self):
        with connect() as conn:
            self.assertIsNone(sv.enter_from_travel(conn, {"from_terrain": "forest", "to": [3, 4]},
                                                   location_id=5, turn=1))
            self.assertIsNone(sv.enter_from_travel(conn, {"settlement_id": "S3", "from_terrain": "town",
                                                          "to": [3, 4]}, location_id=5, turn=1))
            self.assertIsNone(sv.enter_from_travel(conn, None, location_id=5, turn=1))
            self.assertEqual(sv.list_visits(conn), [])

    def test_enter_from_travel_records_the_step(self):
        travel = {
            "settlement_id": "S3", "from_terrain": "forest", "terrain": "town", "to": [12, 7], "minutes": 25,
            "settlement": {"id": "S3", "state": "town", "name": "Ashbarrow", "ruler_power_rank": 57},
        }
        with connect() as conn:
            result = sv.enter_from_travel(conn, travel, location_id=5, turn=9, map_id="board-1",
                                          world_time=_world_time(1, 700))
        self.assertTrue(result["first_visit"])
        self.assertEqual(result["visit"]["settlement_id"], "S3")
        self.assertEqual((result["visit"]["x"], result["visit"]["y"]), (12, 7))
        self.assertEqual(result["visit"]["map_id"], "board-1")
        self.assertEqual(result["visit"]["name"], "Ashbarrow")
        self.assertEqual(result["seed"]["ruler"]["power_rank"], 57)

    def test_enter_from_travel_without_settlement_record(self):
        with connect() as conn:
            result = sv.enter_from_travel(conn, {"settlement_id": "S8", "from_terrain": "plains", "to": [1, 2]},
                                          location_id=3, turn=2)
        self.assertEqual(result["settlement_id"], "S8")
        self.assertEqual(result["visit"]["class"], "town")
        self.assertEqual(result["seed"]["power_source"], "default")

    def test_enter_from_city_uses_city_xy_and_map(self):
        city = {"id": "C7", "name": "Greywater", "band": "large_city", "x": 4021, "y": 977, "population": 40000}
        with connect() as conn:
            result = sv.enter_from_city(conn, city, location_id=11, turn=3, map_id="world-1")
        row = result["visit"]
        self.assertEqual(row["settlement_id"], "C7")
        self.assertEqual(row["map_id"], "world-1")
        self.assertEqual((row["x"], row["y"]), (4021, 977))
        self.assertEqual(row["class"], "city")
        self.assertEqual(row["name"], "Greywater")
        self.assertEqual(row["location_id"], 11)
        self.assertEqual(result["seed"]["ruler"]["power_rank"], 72)
        self.assertEqual(result["seed"]["power_source"], "band")
        self.assertEqual(result["seed"]["ruler"]["role"], "city reeve")

    def test_list_and_state_view_order(self):
        with connect() as conn:
            sv.record_enter(conn, "S1", 2, settlement={"id": "S1", "name": "One"}, map_id="m1")
            sv.record_enter(conn, "S2", 9, settlement={"id": "S2", "name": "Two"}, map_id="m1")
            sv.record_enter(conn, "S3", 5, settlement={"id": "S3", "name": "Three"}, map_id="m2")
            rows = sv.list_visits(conn)
            self.assertEqual([r["settlement_id"] for r in rows], ["S2", "S3", "S1"])
            self.assertEqual([r["settlement_id"] for r in sv.list_visits(conn, map_id="m1")], ["S2", "S1"])
            self.assertEqual([r["settlement_id"] for r in sv.list_visits(conn, limit=1)], ["S2"])
            view = sv.state_view(conn)
            self.assertEqual(list(view.keys()), ["settlement_visits"])
            self.assertEqual([v["settlement_id"] for v in view["settlement_visits"]], ["S2", "S3", "S1"])
            for entry in view["settlement_visits"]:
                self.assertEqual(set(entry.keys()), {"settlement_id", "name", "class", "visit_count",
                                                     "first_visit_turn", "last_visit_turn"})
            self.assertEqual(len(sv.state_view(conn, limit=2)["settlement_visits"]), 2)
            self.assertIsNone(sv.get_visit(conn, "S9"))
            self.assertIsNone(sv.get_visit(conn, ""))

    def test_clear_by_map_id(self):
        with connect() as conn:
            sv.record_enter(conn, "S1", 1, settlement={"id": "S1"}, map_id="m1")
            sv.record_enter(conn, "S2", 1, settlement={"id": "S2"}, map_id="m1")
            sv.record_enter(conn, "S3", 1, settlement={"id": "S3"}, map_id="m2")
            self.assertEqual(sv.clear_visits(conn, map_id="m1"), 2)
            self.assertEqual([r["settlement_id"] for r in sv.list_visits(conn)], ["S3"])
            self.assertEqual(sv.clear_visits(conn), 1)
            self.assertEqual(sv.list_visits(conn), [])
            self.assertEqual(sv.clear_visits(conn), 0)

    def test_no_foreign_writes(self):
        with connect() as conn:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                ("settlement_ruler:S9", "true"),
            )
            before = _table_counts(conn)
            settings_before = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings")}
            sv.record_enter(conn, "S3", 4, settlement={"id": "S3", "state": "town", "ruler_power_rank": 57},
                            location_id=5, world_time=_world_time(1, 600))
            sv.record_enter(conn, "S3", 4, settlement={"id": "S3", "state": "town"}, location_id=5,
                            world_time=_world_time(1, 650))
            sv.enter_from_city(conn, {"id": "C7", "band": "town", "x": 1, "y": 2}, location_id=6, turn=5, map_id="w")
            sv.enter_from_travel(conn, {"settlement_id": "S4", "from_terrain": "forest", "to": [1, 1]},
                                 location_id=7, turn=5)
            sv.state_view(conn)
            sv.clear_visits(conn, map_id="w")
            after = _table_counts(conn)
            settings_after = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings")}
        self.assertEqual(settings_before, settings_after)
        changed = {name for name in set(before) | set(after) if before.get(name) != after.get(name)}
        self.assertEqual(changed, {"settlement_visits"}, changed)
        for name in ("player", "inventory", "npcs", "journal", "settings", "locations", "pacing"):
            self.assertEqual(before.get(name), after.get(name), name)

    def test_import_has_no_side_effects(self):
        import importlib
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            importlib.reload(sv)
        self.assertEqual(buf.getvalue(), "")
        self.assertEqual(sv.REENTRY_GRACE_MINUTES, 30)


if __name__ == "__main__":
    unittest.main()
