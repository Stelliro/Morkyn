"""Heard-about map pins, notice boards, and the in-game quest clock."""

from __future__ import annotations

import os
import random
import tempfile
import unittest
from pathlib import Path

from app.db import connect, init_db
from app.local_intel import (
    BRIBE_GOLD,
    advance_clock,
    advise_notice_percent,
    apply_hint_to_map,
    accept_offered_quest,
    blur_cell,
    compass_word,
    contraband_goods,
    direction_roll,
    ensure_npc_clock,
    expire_offered_quest,
    is_shady,
    list_open_offers,
    magic_is_contraband,
    notice_capacity,
    parse_direction_question,
    place_marker,
    prompt_direction_hint,
    reveal_cells,
    resolve_direction,
    roll_notices_for_cell,
    roll_quest_propensity,
    site_chance,
    stalls_for_district,
    tick_quest_clocks,
    will_tell,
)
from app.quests import create_quest
from app.tile_world import _save_map_payload, generate_scaled_world, get_map, local_map_view, walk_steps
from app.world_scale import build_world


def _post_apoc():
    return {"id": "ash_plain", "age": "post_collapse", "environment": "volcanic"}


class Flat(random.Random):
    def random(self):
        return 0.0

    def randrange(self, start, stop=None, step=1):
        return 0

    def randint(self, a, b):
        return a


class Always(random.Random):
    def random(self):
        return 0.0


class Never(random.Random):
    def random(self):
        return 0.99


class Scripted(random.Random):
    def __init__(self, rolls):
        self.rolls = list(rolls)
        self.i = 0

    def random(self):
        value = self.rolls[self.i]
        self.i += 1
        return value

    def randrange(self, start, stop=None, step=1):
        return 0


def _district(kind, name, anchor, shop_count, perms=None):
    label = {"food": "food", "black_market": "black market"}.get(kind, kind)
    return {
        "id": f"{kind}-{name}",
        "type": kind,
        "label": label,
        "name": name,
        "anchor": list(anchor),
        "shop_count": shop_count,
        "permissions": list(perms or []),
        "tile_count": 40,
    }


def _cell(x, y, side, districts, density=80, seed=7):
    return {
        "x": x,
        "y": y,
        "side": side,
        "density": density,
        "seed": seed,
        "districts": districts,
        "notices": [],
    }


def _world(cells, player, theme="medieval"):
    return {
        "scale": "world",
        "width": 16383,
        "height": 16383,
        "seed": 3,
        "theme": theme,
        "allows_slavery": theme in {"medieval", "ancient", "mixed", "industrial", "post_collapse"},
        "player": {"x": player[0], "y": player[1]},
        "cities": [{"id": "C1", "name": "Harth", "cells": cells}],
        "visited": [f"{player[0]},{player[1]}"],
        "revealed": [],
        "knowledge": {"settlements": [], "danger": [], "notes": [], "sources": []},
    }


def _same_cell_world():
    cell = _cell(
        5,
        5,
        64,
        [
            _district("food", "Granary Ward", [4, 4], 3, ["food"]),
            _district("shopping", "Market Row", [30, 30], 3, ["food", "market"]),
            _district("black_market", "The Pit", [32, 32], 3, ["black_market", "food"]),
            _district("military", "The Barracks", [32, 33], 4, ["weapons"]),
        ],
    )
    return _world([cell], (5, 5), "medieval")


class LocalIntelTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="morkyn-local-intel-")
        root = Path(self._tmp.name)
        self._saved = {
            key: os.environ.get(key)
            for key in (
                "AI_RPG_DB",
                "AI_RPG_CAMPAIGN_SLOTS",
                "AI_RPG_MODEL_TRACE_DIR",
                "AI_RPG_HISTORY_SUMMARY",
                "AI_RPG_SOURCE_INDEX",
                "AI_RPG_CONSOLIDATED_FACTS",
                "AI_RPG_PACK_DIR",
                "AI_RPG_SKILL_LIBRARY",
            )
        }
        os.environ["AI_RPG_DB"] = str(root / "world.db")
        os.environ["AI_RPG_CAMPAIGN_SLOTS"] = str(root / "slots")
        os.environ["AI_RPG_MODEL_TRACE_DIR"] = str(root / "traces")
        os.environ["AI_RPG_HISTORY_SUMMARY"] = str(root / "history.jsonl")
        os.environ["AI_RPG_SOURCE_INDEX"] = str(root / "source")
        os.environ["AI_RPG_CONSOLIDATED_FACTS"] = str(root / "facts.jsonl")
        os.environ["AI_RPG_PACK_DIR"] = str(root / "packs")
        os.environ["AI_RPG_SKILL_LIBRARY"] = str(root / "skills.json")
        self._open: list = []
        init_db()

    def tearDown(self):
        for conn in self._open:
            try:
                conn.close()
            except Exception:
                pass
        self._open.clear()
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmp.cleanup()

    def test_questions_and_contraband(self):
        self.assertIsNone(parse_direction_question("where are you from"))
        closest = parse_direction_question("where is the closest magic shop")
        self.assertEqual(closest["specificity"], "closest")
        self.assertEqual(closest["good"], "magic")
        area = parse_direction_question("where can I buy some food")
        self.assertEqual(area["specificity"], "area")
        self.assertEqual(area["good"], "food")
        self.assertFalse(area["asks_forbidden"])
        self.assertTrue(parse_direction_question("where is the black market")["asks_forbidden"])
        self.assertTrue(magic_is_contraband("medieval"))
        self.assertFalse(magic_is_contraband("space_opera"))
        self.assertFalse(magic_is_contraband("far_future"))
        medieval = contraband_goods("medieval", True)
        for name in ("books", "food", "weapons", "games", "songs", "drugs", "magic", "slavery"):
            self.assertIn(name, medieval)
        self.assertNotIn("magic", contraband_goods("space_opera", False))
        self.assertNotIn("slavery", contraband_goods("medieval", False))
        self.assertEqual(compass_word(1, 1), "southeast")
        self.assertEqual(compass_word(0, -1), "north")
        self.assertEqual(blur_cell(10, 10, 40, 10), (25, 10, False))
        self.assertTrue(blur_cell(10, 10, 12, 10)[2])
        self.assertFalse(is_shady("knight"))
        self.assertTrue(is_shady("night broker"))
        self.assertTrue(is_shady("cult priest"))

    def test_closest_shop_and_district_middle(self):
        world = _same_cell_world()
        clerk = {"id": 4, "role": "clerk", "attitude": "neutral", "trust": 0, "name": "Ned"}
        area = resolve_direction(world, "where can I buy some food", clerk, roll=90, check_success=False)
        self.assertTrue(area["told"])
        self.assertEqual(area["reason"], "willing")
        self.assertEqual(area["place"]["district_type"], "food")
        self.assertEqual(area["place"]["kind"], "district")
        self.assertEqual((area["place"]["fine_x"], area["place"]["fine_y"]), (4, 4))
        self.assertIn("around the middle", area["wording"])
        self.assertIn("Granary Ward", area["wording"])
        self.assertNotIn("closest", area["wording"].lower())
        closest = resolve_direction(world, "where is the closest food shop", clerk, roll=90, check_success=False)
        self.assertTrue(closest["told"])
        self.assertEqual(closest["place"]["kind"], "stall")
        self.assertEqual(closest["place"]["district_type"], "shopping")
        self.assertNotEqual(closest["place"]["district_type"], "black_market")
        self.assertIn("closest food shop", closest["wording"])
        self.assertTrue(closest["exact"])
        weapons = resolve_direction(world, "where is the closest weapon shop", clerk, roll=0, check_success=True)
        self.assertNotEqual((weapons.get("place") or {}).get("district_type"), "military")

    def test_far_place_stops_short_and_forbidden_news_fails_closed(self):
        far = _world(
            [_cell(40, 10, 32, [_district("black_market", "The Pit", [4, 4], 1, ["black_market"])], seed=9)],
            (10, 10),
            "medieval",
        )
        clerk = {"id": 2, "role": "clerk", "attitude": "neutral", "trust": 0, "name": "Ida"}
        refused = resolve_direction(
            far, "where is the closest magic shop", clerk, roll=0, check_success=True, gold=0,
        )
        self.assertFalse(refused["told"])
        self.assertEqual(refused["reason"], "refused")
        self.assertIsNone(refused["x"])
        self.assertIsNone(refused["place"])
        shown = prompt_direction_hint(refused)
        self.assertNotIn("x", shown)
        self.assertNotIn("place", shown)
        fence = {"id": 3, "role": "fence", "attitude": "neutral", "trust": 0, "name": "Quill"}
        told = resolve_direction(
            far, "where is the closest magic shop", fence, roll=10, check_success=False, gold=0,
        )
        self.assertTrue(told["told"])
        self.assertEqual(told["reason"], "shady")
        self.assertEqual((told["x"], told["y"]), (25, 10))
        self.assertEqual(told["place"]["x"], 40)
        self.assertFalse(told["exact"])
        self.assertIn("quiet", told["wording"].lower())
        self.assertNotIn("slave", told["wording"].lower())
        apply_hint_to_map(far, told, save=False)
        self.assertIn("25,10", far["revealed"])
        self.assertNotIn("40,10", far["revealed"])
        self.assertNotIn("25,10", far["visited"])
        bribe = resolve_direction(
            far,
            "where is the black market? I will bribe him",
            clerk,
            roll=10,
            check_success=False,
            gold=5,
        )
        self.assertTrue(bribe["told"])
        self.assertEqual(bribe["reason"], "bribe")
        nobody = resolve_direction(far, "where can I buy food", None, roll=0, check_success=True)
        self.assertFalse(nobody["told"])
        self.assertEqual(nobody["reason"], "nobody")
        self.assertIsNone(nobody["x"])
        opera = _world(
            [_cell(10, 10, 32, [_district("shopping", "Market Row", [8, 8], 3, ["market"])])],
            (10, 10),
            "space_opera",
        )
        ordinary = resolve_direction(
            opera, "where is the closest magic shop", clerk, roll=90, check_success=False,
        )
        self.assertTrue(ordinary["told"])
        self.assertFalse(ordinary["forbidden"])
        self.assertNotIn("quiet", ordinary["wording"].lower())
        self.assertIsNone(resolve_direction({"scale": "board"}, "where can I buy food", clerk))

    def test_markers_only_on_known_cells_and_the_view_keeps_them_separate(self):
        chart = {
            "scale": "world",
            "width": 40,
            "height": 40,
            "seed": 1,
            "theme": "medieval",
            "player": {"x": 2, "y": 2},
            "visited": ["2,2"],
            "revealed": [],
            "cities": [],
            "roads": [],
            "knowledge": {"settlements": [], "danger": [], "notes": [], "sources": []},
        }
        blank = place_marker(chart, 8, 8, "stall")
        self.assertEqual(blank["error"], "That grid is still blank.")
        reveal_cells(chart, 8, 8, 1)
        marked = place_marker(chart, 8, 8, "stall")
        self.assertTrue(marked["ok"])
        self.assertIn("8,8", chart["revealed"])
        self.assertNotIn("8,8", chart["visited"])
        self.assertEqual(place_marker(chart, 10, 8, "nope")["error"], "That grid is still blank.")
        view = local_map_view(chart, radius=1)
        heard = next(tile for tile in view["tiles"] if tile["x"] == 8 and tile["y"] == 8)
        self.assertTrue(heard["revealed"])
        self.assertFalse(heard["visited"])
        self.assertFalse(heard["fog"])
        self.assertNotEqual(heard["state"], "unknown")
        fringe = next(tile for tile in view["tiles"] if tile["x"] == 10 and tile["y"] == 8)
        self.assertTrue(fringe["fog"])
        self.assertFalse(fringe["visited"])
        self.assertFalse(fringe.get("revealed"))
        self.assertNotIn("8,8", chart["visited"])

    def test_filler_stalls_and_notice_spread(self):
        stalls = stalls_for_district(
            _cell(1, 1, 40, [], seed=9),
            _district("food", "Granary", [3, 3], 6, ["food"]),
            theme="medieval",
            slavery=False,
        )
        self.assertEqual(sum(1 for stall in stalls if stall["filler"]), 2)
        self.assertNotEqual((stalls[0]["fine_x"], stalls[0]["fine_y"]), (3, 3))
        self.assertEqual(notice_capacity(7), 0)
        self.assertEqual(notice_capacity(8), 1)
        self.assertEqual(notice_capacity(128), 8)
        self.assertAlmostEqual(site_chance(10, 100), 0.10)
        self.assertAlmostEqual(site_chance(100, 100), 1.0)
        town = _cell(3, 4, 8, [], density=100, seed=1)
        one = roll_notices_for_cell(town, 100, Flat(), city_id="C1")
        self.assertEqual(len(one), 1)
        self.assertEqual(one[0]["kind"], "pinboard")
        self.assertFalse(one[0]["far"])
        self.assertEqual(roll_notices_for_cell(town, 0, Flat(), city_id="C1"), [])
        home = _cell(10, 10, 128, [], density=100, seed=1)
        outer = _cell(11, 10, 8, [], density=20, seed=2)
        notes = roll_notices_for_cell(home, 100, Flat(), city_id="C9", other_cells=[home, outer])
        self.assertEqual(len(notes), 8)
        guilds = [note for note in notes if note["kind"] == "guild"]
        self.assertEqual(len(guilds), 1)
        self.assertLess(len(guilds), 4)
        self.assertFalse(guilds[0]["far"])
        self.assertTrue(all(note["x"] != 11 or note["kind"] != "guild" for note in notes))
        self.assertTrue(any(note["far"] and note["kind"] != "guild" for note in notes))
        alone = roll_notices_for_cell(home, 100, Flat(), city_id="C9", other_cells=[home])
        self.assertTrue(all(not note["far"] for note in alone))
        for theme, bounds in {
            "post_collapse": (4, 12),
            "medieval": (20, 45),
            "industrial": (24, 50),
            "far_future": (15, 40),
            "space_opera": (8, 24),
            "ancient": (12, 30),
            "mixed": (15, 35),
            "timeless": (6, 16),
        }.items():
            for seed in range(12):
                percent = advise_notice_percent(theme, random.Random(seed))
                self.assertGreaterEqual(percent, bounds[0])
                self.assertLessEqual(percent, bounds[1])

    def test_notice_roll_does_not_move_cities_and_stays_inside_them(self):
        quiet = build_world(_post_apoc(), 11, 13, 0)
        busy = build_world(_post_apoc(), 11, 13, 100)
        self.assertEqual([city["name"] for city in quiet["cities"]], [city["name"] for city in busy["cities"]])
        self.assertEqual(
            [(city["x"], city["y"], city["footprint"]) for city in quiet["cities"]],
            [(city["x"], city["y"], city["footprint"]) for city in busy["cities"]],
        )
        self.assertEqual(quiet["notice_percent"], 0)
        self.assertEqual(busy["notice_source"], "given")
        self.assertEqual(busy["revealed"], [])
        found = 0
        for city in busy["cities"]:
            coords = {(int(cell["x"]), int(cell["y"])) for cell in city["cells"]}
            for cell in city["cells"]:
                for notice in cell.get("notices") or []:
                    found += 1
                    self.assertIn((int(notice["x"]), int(notice["y"])), coords)
                    if notice["kind"] == "guild":
                        self.assertGreaterEqual(int(cell.get("side") or 0), 64)
                    if int(cell.get("side") or 0) < 16:
                        self.assertNotEqual(notice["kind"], "guild")
        self.assertGreater(found, 0)
        for city in quiet["cities"]:
            for cell in city["cells"]:
                self.assertEqual(cell.get("notices") or [], [])

    def test_quest_clock_waits_a_day_then_can_lapse(self):
        start = {"offers": 1, "chance": 100, "phase": "waiting", "phase_day": 1}
        stayed, none = advance_clock(dict(start), 0, 1, Always())
        self.assertEqual(none, [])
        self.assertEqual(stayed["phase"], "waiting")
        offered, posted = advance_clock(dict(start), 1, 2, Always())
        self.assertEqual(posted[0]["event"], "offer")
        self.assertEqual(offered["phase"], "offered")
        lapsed, gone = advance_clock(offered, 2, 3, Always())
        self.assertEqual(gone[0]["event"], "expire")
        self.assertEqual(lapsed["phase"], "waiting")
        held = dict(offered)
        held["taken"] = True
        kept, events = advance_clock(held, 2, 40, Always())
        self.assertEqual(events, [])
        self.assertEqual(kept["phase"], "offered")
        jumped, many = advance_clock(dict(start), 1, 5, Always())
        self.assertEqual([item["event"] for item in many], ["offer", "expire", "offer", "expire"])
        self.assertEqual(jumped["phase"], "waiting")
        idle, nothing = advance_clock(
            {"offers": 1, "chance": 5, "phase": "waiting", "phase_day": 0}, 0, 31, Never(),
        )
        self.assertEqual(nothing, [])
        self.assertEqual(idle["phase_day"], 31)
        silent, skipped = advance_clock(
            {"offers": 0, "chance": 100, "phase": "waiting", "phase_day": 0}, 0, 10, Always(),
        )
        self.assertEqual(skipped, [])
        self.assertEqual(silent["last_day"], 10)
        offers, chance = roll_quest_propensity(Scripted([0.0]), shell=True, role="")
        self.assertTrue(offers)
        self.assertEqual(chance, 2)
        self.assertEqual(roll_quest_propensity(Scripted([0.2]), shell=True, role="")[0], False)
        self.assertTrue(roll_quest_propensity(Scripted([0.5]), role="guild herald")[0])
        self.assertEqual(roll_quest_propensity(Scripted([0.5]), role="baker")[0], False)
        self.assertTrue(roll_quest_propensity(Scripted([0.4]), role="baker")[0])

    def _conn(self):
        conn = connect()
        self._open.append(conn)
        return conn

    def test_offered_quest_expires_only_while_untaken(self):
        conn = self._conn()
        kept = create_quest(
            conn, title="Keep this", description="Stay.", steps=[{"title": "Stay"}], status="active",
        )
        expire_offered_quest(conn, kept)
        self.assertEqual(conn.execute("SELECT status FROM quests WHERE id = ?", (kept,)).fetchone()["status"], "active")
        posted = create_quest(
            conn,
            title="A parcel to carry",
            description="Carry it.",
            steps=[{"title": "Carry it"}],
            status="offered",
            notes="clock:npc:4",
        )
        self.assertIsNone(accept_offered_quest(conn, "where is the quest board"))
        self.assertEqual(
            conn.execute("SELECT status FROM quests WHERE id = ?", (posted,)).fetchone()["status"], "offered",
        )
        taken = accept_offered_quest(conn, "I'll take the quest")
        self.assertEqual(taken["title"], "A parcel to carry")
        self.assertEqual(conn.execute("SELECT status FROM quests WHERE id = ?", (posted,)).fetchone()["status"], "active")
        expire_offered_quest(conn, posted)
        self.assertEqual(conn.execute("SELECT status FROM quests WHERE id = ?", (posted,)).fetchone()["status"], "active")
        other = create_quest(
            conn,
            title="Word of a missing crate",
            description="Find it.",
            steps=[{"title": "Find it"}],
            status="offered",
            notes="clock:notice:C1:1:1:0",
        )
        conn.commit()
        offers = list_open_offers()
        self.assertEqual(offers[0]["source"], "notice")
        self.assertEqual(offers[0]["title"], "Word of a missing crate")
        expire_offered_quest(conn, other)
        self.assertEqual(conn.execute("SELECT status FROM quests WHERE id = ?", (other,)).fetchone()["status"], "expired")
        conn.commit()

    def test_day_tick_posts_and_lapses_without_touching_an_accepted_job(self):
        conn = self._conn()
        conn.execute(
            """
            INSERT INTO quest_clocks (subject_key, offers, chance, phase, phase_day, quest_id, last_day)
            VALUES ('npc:9', 1, 100, 'waiting', 1, 0, 1)
            """
        )
        tick_quest_clocks(conn, from_day=1, to_day=2)
        row = conn.execute("SELECT status, title FROM quests WHERE notes = 'clock:npc:9'").fetchone()
        self.assertEqual(row["status"], "offered")
        journal = " ".join(
            item["content"] for item in conn.execute("SELECT content FROM journal").fetchall()
        )
        self.assertIn("A notice is up", journal)
        self.assertNotIn("expired", journal.lower())
        accept_offered_quest(conn, "I accept the job")
        tick_quest_clocks(conn, from_day=2, to_day=12)
        self.assertEqual(
            conn.execute("SELECT status FROM quests WHERE notes = 'clock:npc:9'").fetchone()["status"],
            "active",
        )
        conn.execute(
            """
            INSERT INTO quest_clocks (subject_key, offers, chance, phase, phase_day, quest_id, last_day)
            VALUES ('npc:10', 1, 100, 'waiting', 1, 0, 1)
            """
        )
        tick_quest_clocks(conn, from_day=1, to_day=2)
        tick_quest_clocks(conn, from_day=2, to_day=3)
        self.assertEqual(
            conn.execute("SELECT status FROM quests WHERE notes = 'clock:npc:10'").fetchone()["status"],
            "expired",
        )
        clock = conn.execute("SELECT phase, quest_id FROM quest_clocks WHERE subject_key = 'npc:10'").fetchone()
        self.assertEqual(clock["phase"], "waiting")
        self.assertEqual(int(clock["quest_id"]), 0)
        conn.execute(
            """
            INSERT INTO quest_clocks (subject_key, offers, chance, phase, phase_day, quest_id, last_day)
            VALUES ('npc:11', 1, 100, 'waiting', 1, 0, 1)
            """
        )
        tick_quest_clocks(conn, from_day=1, to_day=5)
        rows = conn.execute("SELECT status FROM quests WHERE notes = 'clock:npc:11'").fetchall()
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(item["status"] == "expired" for item in rows))
        fresh = {"offers": 1, "chance": 100, "phase": "waiting", "phase_day": 5, "quest_id": 0, "last_day": 4}
        # The day a month starts does not post.
        conn.execute(
            """
            INSERT INTO quest_clocks (subject_key, offers, chance, phase, phase_day, quest_id, last_day)
            VALUES ('npc:12', ?, ?, ?, ?, 0, ?)
            """,
            (fresh["offers"], fresh["chance"], fresh["phase"], fresh["phase_day"], fresh["last_day"]),
        )
        tick_quest_clocks(conn, from_day=4, to_day=5)
        self.assertIsNone(conn.execute("SELECT id FROM quests WHERE notes = 'clock:npc:12'").fetchone())
        conn.commit()

    def test_meeting_rolls_a_clock_once(self):
        conn = self._conn()
        loc = conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()
        from app.world import create_shell_npc

        npc = create_shell_npc(conn, int(loc["current_location_id"]), role="passerby")
        key = f"npc:{npc['id']}"
        first = conn.execute("SELECT chance, offers FROM quest_clocks WHERE subject_key = ?", (key,)).fetchone()
        self.assertIsNotNone(first)
        ensure_npc_clock(conn, int(npc["id"]), role="guild herald", shell=False, day=9)
        second = conn.execute("SELECT chance, offers, phase_day FROM quest_clocks WHERE subject_key = ?", (key,)).fetchone()
        self.assertEqual(int(second["chance"]), int(first["chance"]))
        self.assertEqual(int(second["offers"]), int(first["offers"]))
        self.assertNotEqual(int(second["phase_day"]), 9)
        conn.commit()

    def test_directions_charge_a_bribe_and_open_only_the_told_patch(self):
        generate_scaled_world(preset_id="ash_plain", seed=4, density_percent=20, notice_percent=0)
        conn = self._conn()
        chart = get_map(None, conn=conn)
        px, py = int(chart["player"]["x"]), int(chart["player"]["y"])
        chart["theme"] = "medieval"
        chart["cities"] = [
            {
                "id": "C1",
                "name": "Harth",
                "cells": [
                    _cell(
                        px,
                        py,
                        32,
                        [
                            _district("food", "Granary Ward", [4, 4], 2, ["food"]),
                            _district("black_market", "The Pit", [8, 8], 1, ["black_market"]),
                        ],
                        seed=3,
                    )
                ],
            }
        ]
        _save_map_payload(chart, conn=conn)
        loc = conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()
        conn.execute("UPDATE player SET gold = 10 WHERE id = 1")
        from app.world import create_shell_npc

        npc = create_shell_npc(conn, int(loc["current_location_id"]), role="clerk")
        question = "where is the black market? I will bribe him"
        for extra in range(80):
            candidate = question + (" please" * extra)
            if direction_roll(1, int(npc["id"]), candidate.lower()) < 35:
                question = candidate
                break
        self.assertLess(direction_roll(1, int(npc["id"]), question.lower()), 35)
        from app.local_intel import apply_turn_intel

        food = apply_turn_intel(conn, "where can I buy some food", 1)
        self.assertIn("map marks", food)
        self.assertEqual(int(conn.execute("SELECT gold FROM player WHERE id = 1").fetchone()["gold"]), 10)
        paid = apply_turn_intel(conn, question, 1)
        self.assertIn("paid", paid.lower())
        self.assertEqual(
            int(conn.execute("SELECT gold FROM player WHERE id = 1").fetchone()["gold"]),
            10 - BRIBE_GOLD,
        )
        conn.commit()
        saved = get_map()
        self.assertTrue(saved["revealed"])
        self.assertTrue(set(saved["revealed"]).isdisjoint({"40,10"}))

    def test_reveal_survives_a_walk_and_slash_commands_do_not_call_the_model(self):
        from app.debug_commands import handle_command

        missing = handle_command("/reveal 1 1")
        self.assertFalse(missing["ok"])
        self.assertIn("no map", missing["error"].lower())
        self.assertFalse(missing["advanced_turn"])
        generate_scaled_world(preset_id="ash_plain", seed=11, density_percent=13, notice_percent=100)
        chart = get_map()
        self.assertEqual(chart["tiles"], [])
        self.assertEqual(chart["notice_percent"], 100)
        self.assertEqual(chart["notice_source"], "given")
        px, py = int(chart["player"]["x"]), int(chart["player"]["y"])
        far_x, far_y = min(16382, px + 30), py
        reveal_cells(chart, far_x, far_y, 1)
        _save_map_payload(chart)
        walk_steps(chart, "east", 1, save=True)
        again = get_map()
        key = f"{far_x},{far_y}"
        self.assertIn(key, again["revealed"])
        self.assertNotIn(key, again["visited"])
        self.assertEqual(again["tiles"], [])
        self.assertEqual(again["notice_percent"], 100)
        found = False
        for city in again["cities"]:
            coords = {(int(cell["x"]), int(cell["y"])) for cell in city["cells"]}
            for cell in city["cells"]:
                for notice in cell.get("notices") or []:
                    found = True
                    self.assertIn((int(notice["x"]), int(notice["y"])), coords)
        self.assertTrue(found)
        blank = handle_command("/mark 1 1 nowhere")
        self.assertFalse(blank["ok"])
        self.assertEqual(blank["error"], "That grid is still blank.")
        opened = handle_command("/reveal 1 1 1 rumor")
        self.assertTrue(opened["ok"])
        self.assertIn("Revealed", opened["answer"])
        pinned = handle_command("/mark 1 1 rumor")
        self.assertTrue(pinned["ok"])
        here = handle_command("/mark here camp")
        self.assertTrue(here["ok"])
        off = handle_command("/reveal 20000 1")
        self.assertIn("off the map", off["error"].lower())
        from app.llm import HANDOFF_BASE_CONTEXT_KEYS
        from app.prompts import build_user_prompt
        from app.turn_dsl import build_dsl_user_prompt

        self.assertIn("direction_hint", HANDOFF_BASE_CONTEXT_KEYS)
        self.assertIn("open_offers", HANDOFF_BASE_CONTEXT_KEYS)
        wording = "The food district is east of here, around the middle of Granary Ward."
        prompt = build_user_prompt(
            {
                "direction_hint": {"told": True, "wording": wording, "x": 3, "y": 4},
                "open_offers": [{"title": "A parcel to carry", "source": "person"}],
            },
            "where can I buy food",
        )
        self.assertIn("world_state.direction_hint", prompt)
        self.assertIn("world_state.open_offers", prompt)
        self.assertIn(wording, prompt)
        refused = build_user_prompt(
            {"direction_hint": {"told": False, "reason": "refused"}},
            "where is the black market",
        )
        self.assertIn("do not name a location", refused.lower())
        dsl = build_dsl_user_prompt(
            {
                "map_space": {
                    "width": 16383,
                    "height": 16383,
                    "scale": "world",
                    "step_budget": 4,
                    "player": {"x": 1, "y": 1},
                },
                "direction_hint": {"told": True, "wording": wording},
            },
            "where can I buy food",
        )
        self.assertIn("direction_hint.wording", dsl)
        self.assertIn("One step does not cross inside a city.", dsl)


if __name__ == "__main__":
    unittest.main()
