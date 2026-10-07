"""
Town grid, slice B (docs/TownGrid.md 4-6, 9): the player inside a town.

The player asked to zoom into a town, follow its roads and find its shops. Slice
A laid roads and plots over each city cell. These tests hold the engine rules
that put the player on that grid: entering and leaving through gates, walking
the roads for in-game minutes, typed and model moves resolving to real plots,
plots becoming places only when the player goes in, the draft's "places here",
knowledge, and rewind. No model is called (writer-off fixtures).
"""
from __future__ import annotations

import json
import math
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-town-move-"))
os.environ.update(isolated_data_env(str(_TMP)))
for _key, _name in (
    ("AI_RPG_IDEA_BANK", "idea_bank.json"),
    ("AI_RPG_LAUNCHER_PREFS", "launcher_prefs.json"),
    ("AI_RPG_SKILL_LIBRARY", "skill_library.json"),
):
    os.environ.setdefault(_key, str(_TMP / _name))
os.environ.setdefault("AI_RPG_PACK_DIR", str(_TMP / "packs"))
assert "STELLIROS_WORKSHOP" not in os.environ["AI_RPG_DB"]
WRITER_OFF = {
    "AI_RPG_NARRATION_PIPELINE": "0",
    "AI_RPG_NARRATION_PIPELINE_CONSOLIDATE": "1",
    "AI_RPG_FAST_VERIFICATION": "1",
    "AI_RPG_DSL_SKIP_VERIFY": "1",
    "AI_RPG_DRAFT_MODE": "dsl",
}

from app import main, tile_world, town_grid as tg, town_moves as tm, turn_dsl, venues, world  # noqa: E402
from app.db import connect, init_db  # noqa: E402
from app.tile_world import _save_map_payload, generate_scaled_world, get_map  # noqa: E402

_BASE: Path | None = None
_COPIES = 0


def _base() -> Path:
    global _BASE
    if _BASE is None:
        os.environ["AI_RPG_DB"] = str(_TMP / "base.db")
        init_db()
        generate_scaled_world(preset_id="forest_march", seed=20261007, density_percent=60, notice_percent=40)
        _BASE = _TMP / "base.db"
    return _BASE


def _fresh() -> dict:
    """A copy of the base world in its own database file; the chart."""
    global _COPIES
    base = _base()
    _COPIES += 1
    target = _TMP / f"world_{_COPIES}.db"
    shutil.copy(base, target)
    os.environ["AI_RPG_DB"] = str(target)
    tg.clear_caches()
    return get_map(None)


def _city(chart: dict) -> tuple[dict, dict]:
    return tg._locate(chart, *tm.player_cell(chart))


def _plan(text: str) -> dict:
    with connect() as conn:
        return tm.plan_turn(conn, text)


def _apply(town_turn: dict, result: dict | None = None) -> dict:
    result = result if result is not None else {"player": {}}
    with connect() as conn:
        report = tm.apply_town_turn(conn, town_turn, result, None, turn=1)
    return report or {}


def _pos() -> dict | None:
    with connect() as conn:
        return tm.get_position(conn)


def _scalar(sql: str, *args):
    with connect() as conn:
        row = conn.execute(sql, args).fetchone()
    return row[0] if row else None


def _place_player(chart: dict, cx: int, cy: int, came_from=None) -> dict:
    chart["player"] = {"x": cx, "y": cy}
    with connect() as conn:
        _save_map_payload(chart, conn=conn)
        pos = tm.enter_town(conn, chart, came_from)
    return pos


def _expected_minutes(legs: list[dict]) -> int:
    total = 0.0
    steps = 0
    for k, leg in enumerate(legs):
        total += (len(leg["tiles"]) - 1) * tg.tile_minutes(int(leg["side"]))
        steps += len(leg["tiles"]) - 1
        if k:
            total += tg.tile_minutes(int(leg["side"]))
            steps += 1
    return max(1, math.ceil(total - 1e-9)) if steps else 0


def _fake(narration: str, seen: dict | None = None, **extra):
    def generate(context, model_input):
        if seen is not None:
            seen["contract"] = context.get("movement_contract")
            seen["cast"] = context.get("cast_options")
        return {
            "scene_plan": {"goal": "go on", "focus_points": []},
            "narration_segments": [{"label": "scene", "text": narration}],
            "narration": narration,
            "player": dict(extra.pop("player", {}) or {}),
            "self_check": {"passed": True, "issues_found": [], "corrections_made": []},
            "turn_summary": "the player goes on",
            "scene_focus": "action",
            **extra,
        }

    return generate


def _play(text: str, narration: str, seen: dict | None = None, **extra) -> dict:
    with mock.patch.dict(os.environ, WRITER_OFF), mock.patch.object(world, "generate_turn", side_effect=_fake(narration, seen, **extra)):
        db = os.environ["AI_RPG_DB"]
        out = world.play_turn(text)
        os.environ["AI_RPG_DB"] = db
        return out


def _kind_plot(town: dict, kind: str) -> dict | None:
    return next((p for p in town["plots"] if p.get("vk") == kind and p.get("k") in ("shop", "service") and p.get("f")), None)


class EnterAndLeave(unittest.TestCase):
    def setUp(self):
        self.chart = _fresh()
        self.city, self.cell = _city(self.chart)
        self.cells = tg._city_cells(self.city)

    def test_enter_at_a_gate(self):
        ports = tg.city_ports(self.chart, self.city)
        found = None
        for (cx, cy), items in sorted(ports.items()):
            for port in items:
                if port.get("gate"):
                    found = (cx, cy, port)
                    break
            if found:
                break
        self.assertIsNotNone(found, "the city has no gate")
        cx, cy, port = found
        step = {"N": (0, -1), "S": (0, 1), "E": (1, 0), "W": (-1, 0)}[port["edge"]]
        came_from = (cx + step[0], cy + step[1])
        self.assertNotIn(came_from, self.cells)
        pos = _place_player(self.chart, cx, cy, came_from)
        with connect() as conn:
            town = tg.get_cell(conn, self.chart, cx, cy)
        gate = next((p for p in town["plots"] if p.get("k") == "gate" and p.get("gate") == port["gate"]), None)
        expected = tuple(gate["f"]) if gate else tg.port_tile(port, town["side"])
        self.assertEqual((pos["fx"], pos["fy"]), tuple(expected))
        self.assertTrue(town["roads"][pos["fy"] * town["side"] + pos["fx"]])
        self.assertEqual(tm.player_cell(get_map(None)), (cx, cy))

    def test_enter_at_a_gateless_edge(self):
        ports = tg.city_ports(self.chart, self.city)
        found = None
        for (cx, cy), cell in sorted(self.cells.items()):
            gated = {p["edge"] for p in ports.get((cx, cy), []) if p.get("gate")}
            for edge, (dx, dy) in (("N", (0, -1)), ("S", (0, 1)), ("E", (1, 0)), ("W", (-1, 0))):
                if (cx + dx, cy + dy) not in self.cells and edge not in gated:
                    found = (cx, cy, edge, (cx + dx, cy + dy))
                    break
            if found:
                break
        self.assertIsNotNone(found)
        cx, cy, edge, came_from = found
        pos = _place_player(self.chart, cx, cy, came_from)
        with connect() as conn:
            town = tg.get_cell(conn, self.chart, cx, cy)
        side = town["side"]
        gate = next((p for p in town["plots"] if p.get("k") == "gate" and p.get("gate") == {"N": "north", "S": "south", "E": "east", "W": "west"}[edge]), None)
        self.assertIsNone(gate)
        mid = side // 2
        target = {"N": (mid, 0), "S": (mid, side - 1), "W": (0, mid), "E": (side - 1, mid)}[edge]
        self.assertEqual((pos["fx"], pos["fy"]), tuple(tg._nearest_road_tile(town["roads"], side, *target)))

    def test_cross_a_shared_edge(self):
        here = tm.player_cell(self.chart)
        nxt = next((x, y) for x, y in ((here[0] + 1, here[1]), (here[0], here[1] + 1), (here[0] - 1, here[1]), (here[0], here[1] - 1)) if (x, y) in self.cells)
        tt = _plan("I look around.")
        _apply(tt)
        with connect() as conn:
            other = tg.get_cell(conn, self.chart, *nxt, create=True)
            plot = next(p for p in other["plots"] if p.get("k") in ("shop", "service") and p.get("f"))
            plan = tm.plan_to_plot(conn, get_map(None, conn=conn), tm.get_position(conn), plot["id"], enter=False, rule="town_walk")
        self.assertGreaterEqual(len(plan["legs"]), 2)
        self.assertEqual([(l["cx"], l["cy"]) for l in plan["legs"]][-1], nxt)
        self.assertEqual(plan["minutes"], _expected_minutes(plan["legs"]))
        _apply({"position": tt["position"], "plan": plan})
        pos = _pos()
        self.assertEqual((pos["cx"], pos["cy"]), nxt)
        self.assertEqual(tm.player_cell(get_map(None)), nxt, "the world marker follows the town walk")
        self.assertEqual((pos["fx"], pos["fy"]), tuple(plot["f"]))

    def test_leave_by_a_gate(self):
        _apply(_plan("I look around."))
        tt = _plan("I leave town through the gate.")
        plan = tt["plan"]
        self.assertEqual(plan["rule"], "town_leave")
        if plan.get("partial"):
            self.skipTest("the nearest gate is beyond one turn's walk in this city")
        report = _apply(tt)
        self.assertTrue(report.get("left"))
        self.assertIsNone(_pos())
        marker = tm.player_cell(get_map(None))
        self.assertIsNone(tg._locate(get_map(None), *marker), "leaving puts the marker outside the city")

    def test_a_world_step_out_clears_the_position(self):
        _apply(_plan("I look around."))
        self.assertIsNotNone(_pos())
        chart = get_map(None)
        start = tm.player_cell(chart)
        outside = None
        for x in range(start[0] - 12, start[0] + 13):
            if tg._locate(chart, x, start[1]) is None:
                outside = (x, start[1])
                break
        chart["player"] = {"x": outside[0], "y": outside[1]}
        with connect() as conn:
            _save_map_payload(chart, conn=conn)
            report = tm.sync_after_world_move(conn, chart, start)
        self.assertEqual(report["status"], "left")
        self.assertIsNone(_pos())


class Walking(unittest.TestCase):
    def setUp(self):
        self.chart = _fresh()
        self.city, self.cell = _city(self.chart)
        _apply(_plan("I look around."))

    def test_minutes_are_the_path_sum_at_side_128(self):
        tt = _plan("I go to the bakery.")
        plan = tt["plan"]
        self.assertEqual(plan["rule"], "town_walk")
        self.assertEqual(plan["legs"][0]["side"], 128)
        self.assertEqual(plan["minutes"], _expected_minutes(plan["legs"]))

    def test_minutes_are_the_path_sum_at_a_smaller_side(self):
        chart = get_map(None)
        small = None
        for city in chart["cities"]:
            for cell in city["cells"]:
                if 40 <= int(cell["side"]) <= 64:
                    small = (city, cell)
                    break
            if small:
                break
        self.assertIsNotNone(small)
        city, cell = small
        pos = _place_player(chart, int(cell["x"]), int(cell["y"]))
        with connect() as conn:
            town = tg.get_cell(conn, get_map(None, conn=conn), int(cell["x"]), int(cell["y"]))
            far = max((p for p in town["plots"] if p.get("f") and p.get("k") in ("shop", "service", "house")),
                      key=lambda p: abs(p["f"][0] - pos["fx"]) + abs(p["f"][1] - pos["fy"]))
            plan = tm.plan_to_plot(conn, get_map(None, conn=conn), pos, far["id"], enter=False, rule="town_walk")
        self.assertEqual(plan["legs"][0]["side"], int(cell["side"]))
        self.assertEqual(plan["minutes"], _expected_minutes(plan["legs"]))
        self.assertGreater(plan["minutes"], 0)

    def test_a_long_walk_stops_at_the_budget(self):
        self.assertEqual(tg.town_walk_budget(), 40)
        cells = tg._city_cells(self.city)
        here = tm.player_cell(self.chart)
        far = max(cells, key=lambda xy: abs(xy[0] - here[0]) + abs(xy[1] - here[1]))
        with connect() as conn:
            pos = tm.get_position(conn)
            source = tm._CellSource(conn, get_map(None, conn=conn), generate=True, cap=9)
            far_town = source.get(*far)
            goal = next(p for p in far_town["plots"] if p.get("f"))
            goals = {goal["f"][1] * far_town["side"] + goal["f"][0]}
            full = tm._walk(source, self.city, (pos["cx"], pos["cy"], tm._pos_index(pos, 128)), far, goals, budget=1e9)
            budget = max(2.0, full["minutes"] * 2 / 3)
            cut = tm._walk(source, self.city, (pos["cx"], pos["cy"], tm._pos_index(pos, 128)), far, goals, budget=budget)
        self.assertFalse(full["partial"])
        self.assertTrue(cut["partial"])
        self.assertLessEqual(cut["minutes"], math.ceil(budget))
        self.assertGreater(cut["remaining_minutes"], 0)
        self.assertFalse(cut["reached"])

    def test_an_energy_blocked_walk_changes_nothing(self):
        with connect() as conn:
            conn.execute("UPDATE player SET energy = 0, fatigue = 0 WHERE id = 1")
        tt = _plan("I leave town through the gate.")
        plan = tt["plan"]
        self.assertTrue(plan and plan.get("minutes", 0) > 0)
        with connect() as conn:
            from app.player_resources import preview_travel_spend

            need = preview_travel_spend(conn, terrain="city", minutes=plan["minutes"], hard_block=True)
        if not need["blocked"]:
            self.skipTest("this walk costs no energy")
        before = (_pos(), tm.player_cell(get_map(None)), _scalar("SELECT COUNT(*) FROM town_seen"),
                  _scalar("SELECT value FROM pacing WHERE key = 'world_minute'"))
        report = _apply(tt)
        self.assertTrue(report.get("blocked"))
        after = (_pos(), tm.player_cell(get_map(None)), _scalar("SELECT COUNT(*) FROM town_seen"),
                 _scalar("SELECT value FROM pacing WHERE key = 'world_minute'"))
        self.assertEqual(before, after)
        self.assertIn("blocked", tt["contract"])

    def test_confinement_refuses_a_town_walk(self):
        with connect() as conn:
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('movement_locked', 'true')")
        before = _pos()
        tt = _plan("I go to the bakery.")
        self.assertEqual(tt["plan"]["rule"], "town_locked")
        self.assertIn("blocked", tt["contract"])
        _apply(tt)
        self.assertEqual(_pos(), before)
        with self.assertRaises(main.HTTPException) as caught:
            main.api_town_walk(main.TownWalkRequest(cx=before["cx"], cy=before["cy"], fx=before["fx"], fy=before["fy"]))
        self.assertEqual(caught.exception.status_code, 409)

    def test_a_walk_spends_on_the_callers_connection(self):
        def refuse(*_a, **_k):
            raise AssertionError("a second connection was opened")

        with connect() as conn:
            before = world._world_minute(conn)
        town = None
        with connect() as conn:
            pos = tm.get_position(conn)
            town = tg.stored_cell(conn, get_map(None, conn=conn), pos["cx"], pos["cy"])
            plot = max((p for p in town["plots"] if p.get("k") == "shop" and p.get("f")
                        and abs(p["f"][0] - pos["fx"]) + abs(p["f"][1] - pos["fy"]) <= 40),
                       key=lambda p: abs(p["f"][0] - pos["fx"]) + abs(p["f"][1] - pos["fy"]))
            # The UI offers only plots the player can see.
            tg.record_seen(conn, get_map(None, conn=conn)["id"], pos["cx"], pos["cy"], town["side"],
                           road_tiles=[plot["f"][1] * town["side"] + plot["f"][0]])
            with mock.patch.object(world, "connect", side_effect=refuse), \
                    mock.patch.object(tile_world, "connect", side_effect=refuse):
                walked = tm.click_walk(conn, plot_ref=plot["id"])
        self.assertGreater(walked["plan"]["minutes"], 0)
        with connect() as conn:
            after = world._world_minute(conn)
        self.assertEqual(after - before, walked["plan"]["minutes"])
        self.assertEqual((_pos()["fx"], _pos()["fy"]), tuple(plot["f"]))

    def test_the_click_walk_route(self):
        with connect() as conn:
            pos = tm.get_position(conn)
            town = tg.stored_cell(conn, get_map(None, conn=conn), pos["cx"], pos["cy"])
        known = tm._Knowledge
        out = main.api_town_walk(main.TownWalkRequest(cx=pos["cx"], cy=pos["cy"], fx=pos["fx"] + 6, fy=pos["fy"]))
        self.assertTrue(out["ok"])
        self.assertTrue(out["view"]["available"])
        self.assertEqual(out["view"]["player"]["cx"], pos["cx"])
        self.assertIsNotNone(known)
        with self.assertRaises(main.HTTPException) as caught:
            main.api_town_walk(main.TownWalkRequest(plot_id="C0.0.0.0"))
        self.assertEqual(caught.exception.status_code, 400)


class TypedTargets(unittest.TestCase):
    def setUp(self):
        self.chart = _fresh()
        self.city, self.cell = _city(self.chart)
        _apply(_plan("I look around."))

    def test_a_trade_goes_to_the_nearest_generated_plot(self):
        tt = _plan("I go to the bakery.")
        plan = tt["plan"]
        self.assertIn(plan["found_by"], ("known", "generated", "lookup"))
        self.assertEqual(plan["target"]["vk"], "bakery")
        self.assertTrue(plan["reached"])
        self.assertEqual(tt["contract"]["arrived"]["name"], plan["target"]["name"])

    def test_a_known_plot_comes_before_a_nearer_unknown_one(self):
        with connect() as conn:
            pos = tm.get_position(conn)
            chart = get_map(None, conn=conn)
            town = tg.stored_cell(conn, chart, pos["cx"], pos["cy"])
            bakeries = [p for p in town["plots"] if p.get("vk") == "bakery" and p.get("f")]
            if len(bakeries) < 2:
                self.skipTest("one bakery only")
            far = max(bakeries, key=lambda p: abs(p["f"][0] - pos["fx"]) + abs(p["f"][1] - pos["fy"]))
            tg.record_seen(conn, chart["id"], pos["cx"], pos["cy"], town["side"], plot_ns=[far["n"]])
        plan = _plan("I go back to the bakery.")["plan"]
        self.assertEqual(plan["found_by"], "known")
        self.assertEqual(plan["target"]["plot"], far["id"])

    def test_a_plot_name_the_player_knows(self):
        with connect() as conn:
            pos = tm.get_position(conn)
            chart = get_map(None, conn=conn)
            town = tg.stored_cell(conn, chart, pos["cx"], pos["cy"])
            shop = next(p for p in town["plots"] if p.get("k") == "shop" and p.get("name") and p.get("f")
                        and venues.venue_kind_from_name(p["name"]) == p.get("vk"))
            tg.record_seen(conn, chart["id"], pos["cx"], pos["cy"], town["side"], plot_ns=[shop["n"]])
        plan = _plan(f"I head back to {shop['name']}.")["plan"]
        self.assertEqual(plan["target"]["plot"], shop["id"])
        self.assertEqual(plan["kind"], "walk")
        plan = _plan(f"I walk over to {shop['name']} and go inside.")["plan"]
        self.assertEqual(plan["kind"], "enter")

    def test_enter_the_inn_at_its_door(self):
        with connect() as conn:
            pos = tm.get_position(conn)
            chart = get_map(None, conn=conn)
            town = tg.stored_cell(conn, chart, pos["cx"], pos["cy"])
            inn = next((p for p in town["plots"] if p.get("vk") in ("inn", "tavern") and p.get("f")), None)
            if inn is None:
                self.skipTest("no inn here")
            walk = tm.plan_to_plot(conn, chart, pos, inn["id"], enter=False, rule="town_walk")
        _apply({"position": pos, "plan": walk})
        word = "inn" if inn["vk"] == "inn" else "tavern"
        tt = _plan(f"I go into the {word}.")
        plan = tt["plan"]
        self.assertEqual(plan["kind"], "enter")
        self.assertEqual(plan["target"]["plot"], inn["id"])
        self.assertEqual(plan["minutes"], 0)

    def test_a_street_name(self):
        with connect() as conn:
            pos = tm.get_position(conn)
            chart = get_map(None, conn=conn)
            town = tg.stored_cell(conn, chart, pos["cx"], pos["cy"])
            here = tm.street_at(town, tm._pos_index(pos, town["side"]))
            seg = next(s for s in town["segments"] if s.get("name_id") is not None
                       and town["streets"][s["name_id"]] != here and s["cls"] in (tg.ROAD_AVENUE, tg.ROAD_MAIN))
            name = town["streets"][seg["name_id"]]
        plan = _plan(f"I head to {name}.")["plan"]
        self.assertEqual(plan["target"].get("street"), name)
        end = plan["end"]
        self.assertIn(end[2], set(tg._segment_tiles(seg, town["side"])) | {
            i for s in town["segments"] if s.get("name_id") == seg["name_id"] for i in tg._segment_tiles(s, town["side"])
        })

    def test_leave_the_shop(self):
        tt = _plan("I go into the bakery.")
        _apply(tt, {"player": {}})
        with connect() as conn:
            row = conn.execute("SELECT code FROM locations WHERE plot_id = ?", (tt["plan"]["target"]["plot"],)).fetchone()
            conn.execute("UPDATE player SET current_location_id = (SELECT id FROM locations WHERE code = ?) WHERE id = 1", (row["code"],))
        tt = _plan("I step back out into the street.")
        self.assertEqual(tt["plan"]["rule"], "town_exit")
        result = {"player": {}}
        _apply(tt, result)
        settle = _scalar("SELECT code FROM locations WHERE city_id = ? AND plot_id = '' AND kind = ''", self.city["id"])
        self.assertEqual(result["player"]["move_to_location_code"], settle)
        self.assertEqual(_pos()["inside"], "")

    def test_a_trade_a_fully_generated_small_city_lacks(self):
        chart = get_map(None)
        small = min((c for c in chart["cities"] if len(c["cells"]) <= tm.SMALL_CITY_CELLS),
                    key=lambda c: (len(c["cells"]), c["id"]))
        cell = small["cells"][0]
        _place_player(chart, int(cell["x"]), int(cell["y"]))
        with connect() as conn:
            for c in small["cells"]:
                tg.get_cell(conn, get_map(None, conn=conn), int(c["x"]), int(c["y"]), create=True)
            kinds = set()
            for c in small["cells"]:
                town = tg.stored_cell(conn, get_map(None, conn=conn), int(c["x"]), int(c["y"]))
                kinds |= {p.get("vk") for p in town["plots"] if p.get("k") in ("shop", "service", "temple")}
            era = world._world_era(conn)
        missing = [k for k in ("library", "jeweller", "bathhouse", "armorer", "alchemist", "counting_house", "scribe",
                               "tanner", "apothecary", "tailor")
                   if k not in kinds and venues.kind_fits_era(k, era)]
        self.assertTrue(missing)
        word = venues.kind_label(missing[0])
        rows = _scalar("SELECT COUNT(*) FROM locations")
        tt = _plan(f"I look for a {word}.")
        self.assertEqual(tt["plan"]["rule"], "town_none")
        self.assertIn("none", tt["contract"])
        result = {"player": {"move_to_location": f"The Gilded {word.title()}"}}
        with connect() as conn:
            result["_town_turn"] = tt
            report = tm.resolve_town_movement(conn, result, f"I look for a {word}.", intent="travel", narration="You search.")
        self.assertEqual(report["rule"], "town_none")
        self.assertIsNone(result["player"]["move_to_location"])
        _apply(tt, result)
        self.assertEqual(_scalar("SELECT COUNT(*) FROM locations"), rows, "nothing is minted")

    def test_a_trade_missing_from_a_big_citys_generated_cells(self):
        chart = get_map(None)
        self.city = max(chart["cities"], key=lambda c: (len(c["cells"]), c["id"]))
        cells = tg._city_cells(self.city)
        self.assertGreater(len(cells), tm.SMALL_CITY_CELLS)
        centre = max(self.city["cells"], key=lambda c: (int(c["side"]), -int(c["x"]), -int(c["y"])))
        _place_player(chart, int(centre["x"]), int(centre["y"]))
        self.chart = get_map(None)
        # This city has every common trade somewhere; the test asks for one the
        # cells a lookup may reach do not hold, by hiding the bakeries.
        real = tm._kind_matches

        def no_bakery(plot, kind):
            return False if kind == "bakery" else real(plot, kind)

        before = _scalar("SELECT COUNT(*) FROM town_cells")
        rows = _scalar("SELECT COUNT(*) FROM locations")
        with mock.patch.object(tm, "_kind_matches", side_effect=no_bakery):
            tt = _plan("I look for a bakery.")
        self.assertEqual(tt["plan"]["rule"], "town_unknown", tt["plan"])
        made = _scalar("SELECT COUNT(*) FROM town_cells") - before
        self.assertGreater(made, 0, "the lookup asked the nearest cells")
        self.assertLessEqual(made, tg.TOWN_LOOKUP_CELLS)
        self.assertLess(_scalar("SELECT COUNT(*) FROM town_cells"), len(cells), "the city was not generated whole")
        self.assertEqual(_scalar("SELECT COUNT(*) FROM locations"), rows)
        self.assertIn("ask around", tt["contract"]["none"])


class PlanBeforePrompt(unittest.TestCase):
    def setUp(self):
        self.chart = _fresh()

    def test_the_prompt_carries_the_plan_and_the_turn_applies_it(self):
        seen: dict = {}
        _play("I look around the street.", "You stand in the lane and look about.", seen)
        town = (seen["contract"] or {}).get("town") or {}
        self.assertTrue(town.get("places_here") is not None)
        self.assertNotIn("venue_name_options", seen["contract"])
        self.assertNotIn("venue_kinds_possible", seen["contract"])
        self.assertNotIn("venue_names", seen["cast"] or {})
        with connect() as conn:
            expect = tm.plan_turn(conn, "I go to the bakery.")["plan"]
        out = _play("I go to the bakery.", "You walk down the lane to the bakery door.", seen)
        arrived = seen["contract"]["town"]["arrived"]
        self.assertEqual(arrived["name"], expect["target"]["name"])
        pos = _pos()
        self.assertEqual((pos["cx"], pos["cy"], tm._pos_index(pos, 128)), tuple(expect["end"]))
        self.assertEqual(out["state"]["movement"]["rule"], "town_walk")

    def test_walk_east_to_the_bakery_keeps_the_marker_on_the_town_cell(self):
        _play("I look around.", "You look about.")
        _play("I walk east to the bakery.", "You walk east along the lane to the bakery.",
              map_walk={"direction": "east", "steps": 4})
        pos = _pos()
        self.assertEqual(tm.player_cell(get_map(None)), (pos["cx"], pos["cy"]))

    def test_out_the_gate_hands_off_to_the_world(self):
        _play("I look around.", "You look about.")
        with connect() as conn:
            plan = tm.plan_turn(conn, "I leave town through the gate.")["plan"]
        if plan.get("partial"):
            self.skipTest("the gate is beyond one turn's walk")
        _play("I leave town through the gate.", "You walk out through the gate onto the road.")
        self.assertIsNone(_pos())
        marker = tm.player_cell(get_map(None))
        self.assertIsNone(tg._locate(get_map(None), *marker))


class SettlementAndPlots(unittest.TestCase):
    def setUp(self):
        self.chart = _fresh()
        self.city, self.cell = _city(self.chart)

    def test_an_existing_row_named_like_the_city_is_adopted(self):
        with connect() as conn:
            conn.execute("INSERT INTO locations (code, name, summary) VALUES ('L77', ?, '')", (self.city["name"],))
            row_id = conn.execute("SELECT id FROM locations WHERE code = 'L77'").fetchone()[0]
            got = tm.settlement_row(conn, self.city)
            again = tm.settlement_row(conn, self.city)
        self.assertEqual(got, row_id)
        self.assertEqual(again, row_id)
        self.assertEqual(_scalar("SELECT city_id FROM locations WHERE id = ?", row_id), self.city["id"])

    def test_a_venue_with_the_city_name_forces_the_band_word(self):
        with connect() as conn:
            conn.execute("INSERT INTO locations (code, name, summary, kind) VALUES ('L77', ?, '', 'inn')", (self.city["name"],))
            got = tm.settlement_row(conn, self.city)
            name = conn.execute("SELECT name FROM locations WHERE id = ?", (got,)).fetchone()[0]
        self.assertNotEqual(name, self.city["name"])
        self.assertTrue(name.startswith(self.city["name"]))
        self.assertEqual(venues.venue_kind_from_name(name), "")

    def test_realization_is_idempotent_and_stamped(self):
        _apply(_plan("I look around."))
        with connect() as conn:
            chart = get_map(None, conn=conn)
            pos = tm.get_position(conn)
            town = tg.stored_cell(conn, chart, pos["cx"], pos["cy"])
            shop = next(p for p in town["plots"] if p.get("k") == "shop" and p.get("vk") and p.get("name"))
            first = tm.realize_plot(conn, chart, shop["id"])
            second = tm.realize_plot(conn, chart, shop["id"])
            row = dict(conn.execute("SELECT * FROM locations WHERE id = ?", (first,)).fetchone())
            settle = tm.settlement_row(conn, self.city)
        self.assertEqual(first, second)
        self.assertEqual(row["plot_id"], shop["id"])
        self.assertEqual(row["parent_id"], settle)
        self.assertEqual(row["kind"], shop["vk"])
        hours = venues.default_hours(shop["vk"])
        self.assertEqual((row["open_minute"], row["close_minute"]), hours)
        self.assertEqual(row["name"], shop["name"])

    def test_a_name_clash_gets_the_street_and_an_alias(self):
        _apply(_plan("I look around."))
        with connect() as conn:
            chart = get_map(None, conn=conn)
            pos = tm.get_position(conn)
            town = tg.stored_cell(conn, chart, pos["cx"], pos["cy"])
            shop = next(p for p in town["plots"] if p.get("k") == "shop" and p.get("vk") and p.get("name") and tm._plot_street(town, p))
            conn.execute("INSERT INTO locations (code, name, summary) VALUES ('L88', ?, 'elsewhere')", (shop["name"],))
            got = tm.realize_plot(conn, chart, shop["id"])
            row = dict(conn.execute("SELECT * FROM locations WHERE id = ?", (got,)).fetchone())
            alias = conn.execute("SELECT entity_code FROM aliases WHERE alias = ?", (shop["name"],)).fetchone()
        self.assertEqual(row["name"], f"{shop['name']} on {tm._plot_street(town, shop)}")
        self.assertEqual(alias[0], row["code"])
        self.assertEqual(venues.row_kind(row), shop["vk"])

    def test_a_closed_shop_leaves_the_player_at_the_door(self):
        _apply(_plan("I look around."))
        with connect() as conn:
            pos = tm.get_position(conn)
            town = tg.stored_cell(conn, get_map(None, conn=conn), pos["cx"], pos["cy"])
            bakery = _kind_plot(town, "bakery")
            conn.execute("INSERT OR REPLACE INTO pacing (key, value) VALUES ('world_minute', ?)", (str(23 * 60),))
        rows = _scalar("SELECT COUNT(*) FROM locations")
        tt = _plan("I go into the bakery.")
        plan = tt["plan"]
        self.assertEqual(plan["target"]["vk"], "bakery")
        self.assertFalse(plan["open"])
        self.assertFalse(plan["enter"])
        self.assertIn("closed", tt["contract"]["arrived"]["where"])
        report = _apply(tt)
        self.assertEqual(report.get("refused"), "venue_closed")
        self.assertEqual(_scalar("SELECT COUNT(*) FROM locations WHERE plot_id != ''"), 0)
        self.assertEqual(_pos()["inside"], "")
        self.assertGreaterEqual(_scalar("SELECT COUNT(*) FROM locations"), rows)


class ModelMoves(unittest.TestCase):
    def setUp(self):
        self.chart = _fresh()
        _play("I look around.", "You look about the lane.")

    def _stand_near_a_bakery(self):
        """Two road tiles from the nearest bakery's door: inside the near cap, not at the door."""
        with connect() as conn:
            chart = get_map(None, conn=conn)
            pos = tm.get_position(conn)
            town = tg.stored_cell(conn, chart, pos["cx"], pos["cy"])
            side = town["side"]
            here = tm._pos_index(pos, side)
            bakeries = [p for p in town["plots"] if p.get("vk") == "bakery" and p.get("f")]
            dist = tm._road_dist(town, here)
            door = min(bakeries, key=lambda p: dist.get(p["f"][1] * side + p["f"][0], 10 ** 9))
            around = tm._road_dist(town, door["f"][1] * side + door["f"][0], limit=2)
            spot = next(i for i, d in sorted(around.items(), key=lambda kv: -kv[1])
                        if d == 2 and (tm._frontage_plot(town, i) or {}).get("vk") != "bakery")
            city = tg._locate(chart, pos["cx"], pos["cy"])[0]
            tm.write_position(conn, tm._make_position(chart, city, pos["cx"], pos["cy"], town, spot))

    def test_an_invented_bakery_is_re_aimed_and_renamed(self):
        self._stand_near_a_bakery()
        out = _play("I go inside.", "You push open the door and step into the Blind Owl Bakery.",
                    player={"move_to_location": "Blind Owl Bakery"})
        movement = out["state"]["movement"]
        self.assertEqual(movement["renamed"]["from"], "Blind Owl Bakery")
        real = movement["renamed"]["to"]
        narration = out.get("narration") or (out.get("turn") or {}).get("narration") or ""
        self.assertIn(real, narration)
        self.assertNotIn("Blind Owl Bakery", narration)
        self.assertIsNone(_scalar("SELECT id FROM locations WHERE name = 'Blind Owl Bakery'"))
        self.assertEqual(_scalar("SELECT COUNT(*) FROM locations WHERE kind != '' AND COALESCE(plot_id, '') = ''"), 0)

    def test_an_unshown_move_is_still_dropped(self):
        rows = _scalar("SELECT COUNT(*) FROM locations")
        out = _play('I say, "Nice weather."', "The baker nods and goes back to her bread.",
                    player={"move_to_location": "Blind Owl Bakery"})
        self.assertEqual(out["state"]["movement"]["status"], "dropped_unshown")
        self.assertEqual(_scalar("SELECT COUNT(*) FROM locations"), rows)
        self.assertEqual(_pos()["inside"], "")

    def test_prose_entering_a_listed_plot_enters_it(self):
        # Stand at a bakery door first, then let the prose (no MOVE) go in.
        _play("I go to the bakery.", "You walk down the lane to the bakery door.")
        with connect() as conn:
            pos = tm.get_position(conn)
            town = tg.stored_cell(conn, get_map(None, conn=conn), pos["cx"], pos["cy"])
            door = tm._frontage_plot(town, tm._pos_index(pos, town["side"]))
        self.assertEqual(door.get("vk"), "bakery")
        with mock.patch.object(venues, "is_open", return_value=True):
            out = _play("I look at the loaves in the window.", "You push the door and step inside the bakery, where the air is warm.")
        movement = out["state"]["movement"]
        self.assertEqual(movement["rule"], "town_shown", movement)
        row = _scalar("SELECT id FROM locations WHERE plot_id = ?", door["id"])
        self.assertTrue(row, "the bakery the prose entered is the plot at the door")
        self.assertEqual(_scalar("SELECT current_location_id FROM player WHERE id = 1"), row)

    def test_prose_entering_an_unlisted_kind_mints_nothing(self):
        rows = _scalar("SELECT COUNT(*) FROM locations")
        out = _play("I look at the doors.", "You step inside the observatory, where brass lenses gleam.")
        self.assertEqual(_scalar("SELECT COUNT(*) FROM locations"), rows)
        self.assertNotEqual(out["state"]["movement"].get("rule"), "venue_shown")


class Workplaces(unittest.TestCase):
    def setUp(self):
        self.chart = _fresh()
        self.city, self.cell = _city(self.chart)
        _apply(_plan("I look around."))
        with connect() as conn:
            self.settle = tm.settlement_row(conn, self.city)
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (self.settle,))

    def _npc(self, name: str, role: str) -> int:
        with connect() as conn:
            cur = conn.execute(
                "INSERT INTO npcs (code, location_id, name, role, summary) VALUES (?, ?, ?, ?, '')",
                (world._next_alpha_code(conn), self.settle, name, role),
            )
            return int(cur.lastrowid)

    def test_a_baker_claims_a_bakery_plot_and_no_row_is_made(self):
        npc = self._npc("Hesper Vane", "baker")
        rows = _scalar("SELECT COUNT(*) FROM locations")
        cells = _scalar("SELECT COUNT(*) FROM town_cells")
        with connect() as conn:
            self.assertEqual(world.plan_npc_workplace(conn, npc), 0)
            plan = world.npc_workplace_plan(conn, npc)
        self.assertEqual(plan["kind"], "bakery")
        self.assertTrue(plan["plot_id"])
        found = None
        with connect() as conn:
            found = tm.locate_plot(conn, get_map(None, conn=conn), plan["plot_id"])
        self.assertEqual(found[3]["vk"], "bakery")
        self.assertEqual(plan["name"], found[3]["name"])
        self.assertEqual(_scalar("SELECT COUNT(*) FROM locations"), rows, "planning makes no row")
        self.assertEqual(_scalar("SELECT COUNT(*) FROM town_cells"), cells, "planning generates no cell")
        state = world.get_state()
        hesper = next(n for loc in state["locations"] for n in loc.get("npcs") or [] if n["name"] == "Hesper Vane")
        self.assertEqual(hesper["workplace"], found[3]["name"])
        with connect() as conn:
            venue = world.ensure_npc_workplace(conn, npc)
            row = dict(conn.execute("SELECT * FROM locations WHERE id = ?", (venue,)).fetchone())
        self.assertEqual(row["plot_id"], plan["plot_id"])
        self.assertEqual(row["keeper_npc_id"], npc)

    def test_two_bakers_never_share_a_plot_when_two_are_free(self):
        with connect() as conn:
            pos = tm.get_position(conn)
            town = tg.stored_cell(conn, get_map(None, conn=conn), pos["cx"], pos["cy"])
        if len([p for p in town["plots"] if p.get("vk") == "bakery"]) < 2:
            self.skipTest("one bakery only")
        a, b = self._npc("Hesper Vane", "baker"), self._npc("Orrin Vale", "baker")
        with connect() as conn:
            world.plan_npc_workplace(conn, a)
            world.plan_npc_workplace(conn, b)
            pa, pb = world.npc_workplace_plan(conn, a), world.npc_workplace_plan(conn, b)
        self.assertNotEqual(pa["plot_id"], pb["plot_id"])

    def test_no_plot_of_the_trade_keeps_a_nameless_plan_until_one_is_generated(self):
        with connect() as conn:
            pos = tm.get_position(conn)
            chart = get_map(None, conn=conn)
            kinds = set()
            for xy in tm._generated_cells(conn, chart, self.city["id"]):
                kinds |= {p.get("vk") for p in tg.stored_cell(conn, chart, *xy)["plots"]}
            era = world._world_era(conn)
        self.assertIn("bakery", kinds)
        npc = self._npc("Tamsin Reed", "baker")
        # As if no cell with a bakery had been generated yet.
        with connect() as conn, mock.patch.object(tm, "_generated_cells", return_value=[]):
            world.plan_npc_workplace(conn, npc)
            plan = world.npc_workplace_plan(conn, npc)
        self.assertEqual(plan["name"], "")
        self.assertEqual(plan["plot_id"], "")
        state = world.get_state()
        tamsin = next(n for loc in state["locations"] for n in loc.get("npcs") or [] if n["name"] == "Tamsin Reed")
        self.assertEqual(tamsin["workplace"], f"a {venues.kind_label(plan['kind'])}")
        with connect() as conn, mock.patch.object(tm, "_generated_cells", return_value=[]):
            self.assertEqual(world.ensure_npc_workplace(conn, npc), 0, "an unclaimed plan makes no place")
        rows = _scalar("SELECT COUNT(*) FROM locations WHERE plot_id != ''")
        self.assertEqual(rows, 0)
        with connect() as conn:
            world.plan_npc_workplace(conn, npc)
            again = world.npc_workplace_plan(conn, npc)
        self.assertTrue(again["plot_id"], "claimed once a cell with a bakery is generated")
        self.assertTrue(again["name"])


class ContractAndPrompt(unittest.TestCase):
    def setUp(self):
        self.chart = _fresh()
        _apply(_plan("I look around."))

    def test_places_here_lists_only_seen_plots(self):
        tt = _plan("I look around.")
        places = tt["contract"]["places_here"]
        self.assertLessEqual(len(places), tm.PLACES_MAX)
        with connect() as conn:
            pos = tm.get_position(conn)
            chart = get_map(None, conn=conn)
            town = tg.stored_cell(conn, chart, pos["cx"], pos["cy"])
            know = tm._Knowledge(conn, chart, town)
        names = {p["name"] for p in town["plots"] if p.get("name") and know.name_known(p)}
        for item in places:
            if item["name"]:
                self.assertIn(item["name"], names)

    def test_the_town_bullets_replace_the_general_ones(self):
        context = {"movement_contract": {"town": {"places_here": []}}}
        prompt = turn_dsl.dsl_system_prompt_for(context)
        self.assertNotIn("otherwise name the building and it is created", prompt)
        self.assertNotIn("going in costs the next\n  turn", prompt)
        self.assertNotIn("A hike is at most 4 tiles", prompt)
        self.assertIn("In a town do not WALK.", prompt)
        self.assertIs(turn_dsl.dsl_system_prompt_for({"movement_contract": {}}), turn_dsl.DSL_SYSTEM_PROMPT)
        self.assertIn("otherwise name the building and it is created", turn_dsl.DSL_SYSTEM_PROMPT)

    def test_the_legacy_contract_is_unchanged_outside_a_town(self):
        state = {"current_location": {"code": "L1", "name": "Mosswake Gate", "settlement_size": "village",
                                      "venues_here": []}, "locations": [], "settings": {}}
        contract = world.movement_contract(state, "I walk to the inn.", "travel")
        self.assertIn("venue_rule", contract)
        self.assertIn("venue_kinds_possible", contract)
        self.assertNotIn("town", contract)
        town_state = dict(state, town_contract={"places_here": [], "rule": tm.TOWN_RULE})
        contract = world.movement_contract(town_state, "I walk to the inn.", "travel")
        self.assertIn("town", contract)
        self.assertNotIn("venue_rule", contract)
        self.assertNotIn("venue_name_options", contract)
        self.assertNotIn("WALK", contract["expectation"].replace("Do not WALK", ""))

    def test_the_packet_carries_the_town_block(self):
        from app.prompts import build_user_prompt

        context = {"movement_contract": {"current_location": {"code": "L1", "name": "X"},
                                         "town": {"places_here": [{"name": "A", "kind": "bakery", "where": "here"}]}}}
        packet = json.loads(build_user_prompt(context, "I look around."))
        self.assertEqual(packet["world_state"]["town"]["places_here"][0]["name"], "A")


class Knowledge(unittest.TestCase):
    def setUp(self):
        self.chart = _fresh()
        self.city, self.cell = _city(self.chart)

    def test_a_walk_reveals_the_road_and_reads_signs(self):
        _apply(_plan("I look around."))
        before = _scalar("SELECT COUNT(*) FROM town_seen")
        tt = _plan("I go to the bakery.")
        _apply(tt)
        self.assertGreater(_scalar("SELECT COUNT(*) FROM town_seen"), before)
        with connect() as conn:
            peek = tg.plot_peek(conn, get_map(None, conn=conn), tt["plan"]["target"]["plot"])
        self.assertEqual(peek["name"], tt["plan"]["target"]["name"], "the sign at the door was read")

    def test_a_direction_answer_records_a_told_stall(self):
        from app.local_intel import stalls_for_district
        from app.world_scale import theme_allows_slavery

        theme = str(self.chart.get("theme") or "")
        slavery = bool(self.chart.get("allows_slavery")) or theme_allows_slavery(theme)
        stall, district = None, None
        for d in self.cell["districts"]:
            for s in stalls_for_district(self.cell, d, theme=theme, slavery=slavery):
                if not s["filler"]:
                    stall, district = s, d
                    break
            if stall:
                break
        self.assertIsNotNone(stall)
        with connect() as conn:
            told = tm.record_told(conn, self.chart, dict(stall, kind="stall"), 1)
            self.assertTrue(told.startswith("stall:"))
            self.assertEqual(_scalar("SELECT COUNT(*) FROM town_cells"), 0, "telling generates nothing")
            town = tg.get_cell(conn, get_map(None, conn=conn), int(self.cell["x"]), int(self.cell["y"]), create=True)
            plot = next(p for p in town["plots"] if p.get("st") == told[len("stall:"):])
            peek = tg.plot_peek(conn, get_map(None, conn=conn), plot["id"])
        self.assertEqual(peek["name"], plot["name"])


class Rewind(unittest.TestCase):
    def setUp(self):
        self.chart = _fresh()

    def test_rewinding_a_walk_into_a_plot(self):
        _play("I look around.", "You look about the lane.")
        before_pos = _pos()
        before_seen = _scalar("SELECT MAX(id) FROM town_seen")
        out = _play("I go into the bakery.", "You walk down the lane and step into the bakery.")
        self.assertEqual(out["state"]["movement"]["rule"], "town_enter")
        self.assertTrue(_scalar("SELECT COUNT(*) FROM locations WHERE plot_id != ''"))
        self.assertGreater(_scalar("SELECT MAX(id) FROM town_seen"), before_seen)
        # A stale marker (as if the world walk had not been rewound) is put back.
        chart = get_map(None)
        chart["player"] = {"x": chart["player"]["x"] + 40, "y": chart["player"]["y"]}
        with connect() as conn:
            _save_map_payload(chart, conn=conn)
        world.rewind_last_turn()
        self.assertEqual(_pos(), before_pos)
        self.assertEqual(_scalar("SELECT MAX(id) FROM town_seen"), before_seen)
        self.assertEqual(_scalar("SELECT COUNT(*) FROM locations WHERE plot_id != ''"), 0)
        self.assertEqual(tm.player_cell(get_map(None)), (before_pos["cx"], before_pos["cy"]))


class ReviewFixes(unittest.TestCase):
    """Slice B/C review findings: rewind of in-place writes, town errors, far re-aims, click-walk fog."""

    def setUp(self):
        self.chart = _fresh()
        self.city, self.cell = _city(self.chart)

    def test_rewinding_an_entry_restores_a_keeper_away_from_the_player(self):
        _play("I look around.", "You look about the lane.")
        plot_ref = str(_plan("I go into the bakery.")["plan"]["target"]["plot"])
        plan_json = json.dumps({"name": "probe bakery", "kind": "bakery"})
        with connect() as conn:
            far = conn.execute("INSERT INTO locations (code, name, summary, visit_count) VALUES ('LPROBE', 'Probe Farm', '', 0)").lastrowid
            npc = conn.execute(
                "INSERT INTO npcs (code, name, location_id, workplace_plot, workplace_plan, workplace_id) VALUES (?, 'Probe Baker', ?, ?, ?, 0)",
                (world._next_alpha_code(conn), far, plot_ref, plan_json),
            ).lastrowid
        out = _play("I go into the bakery.", "You walk down the lane and step into the bakery.")
        self.assertEqual(out["state"]["movement"]["rule"], "town_enter")
        self.assertTrue(_scalar("SELECT workplace_id FROM npcs WHERE id = ?", npc))
        world.rewind_last_turn()
        self.assertEqual(_scalar("SELECT COUNT(*) FROM locations WHERE plot_id != ''"), 0)
        self.assertEqual(_scalar("SELECT workplace_id FROM npcs WHERE id = ?", npc), 0)
        self.assertEqual(_scalar("SELECT workplace_plan FROM npcs WHERE id = ?", npc), plan_json)
        self.assertEqual(_scalar("SELECT workplace_plot FROM npcs WHERE id = ?", npc), plot_ref)

    def test_rewinding_the_entry_turn_un_adopts_the_settlement_row(self):
        with connect() as conn:
            row_id = conn.execute(
                "INSERT INTO locations (code, name, summary) VALUES ('L77', ?, '')", (self.city["name"],)
            ).lastrowid
        _play("I look around.", "You look about the lane.")
        self.assertEqual(_scalar("SELECT city_id FROM locations WHERE id = ?", row_id), self.city["id"])
        world.rewind_last_turn()
        self.assertFalse(_scalar("SELECT COALESCE(city_id, '') FROM locations WHERE id = ?", row_id))

    def test_a_town_code_error_falls_back_to_the_legacy_rules(self):
        _play("I look around.", "You look about the lane.")
        rows = _scalar("SELECT COUNT(*) FROM locations")

        def broken(*_a, **_k):
            raise RuntimeError("probe")

        with mock.patch.object(tm, "resolve_town_movement", side_effect=broken):
            out = _play('I say, "Nice weather."', "The baker nods and goes back to her bread.",
                        player={"move_to_location": "Blind Owl Bakery"})
        movement = out["state"]["movement"]
        self.assertEqual(movement["status"], "dropped_unshown", movement)
        self.assertIn("probe", movement.get("town_error", ""))
        self.assertEqual(_scalar("SELECT COUNT(*) FROM locations"), rows)
        self.assertIsNone(_scalar("SELECT id FROM locations WHERE name = 'Blind Owl Bakery'"))

    def test_an_invented_shop_beyond_the_near_cap_is_dropped_not_walked(self):
        _play("I look around.", "You look about the lane.")
        before = _pos()
        rows = _scalar("SELECT COUNT(*) FROM locations")
        with mock.patch.object(tm, "_NEAR_MINUTES", -1):
            out = _play("I go inside.", "You push open the door and step into the Blind Owl Bakery.",
                        player={"move_to_location": "Blind Owl Bakery"})
        movement = out["state"]["movement"]
        self.assertEqual(movement["rule"], "town_far", movement)
        self.assertEqual(movement["prose_mismatch"], "Blind Owl Bakery")
        self.assertNotIn("renamed", movement)
        self.assertEqual(_scalar("SELECT COUNT(*) FROM locations"), rows)
        after = _pos()
        self.assertEqual((after["cx"], after["cy"], after["fx"], after["fy"], after["inside"]),
                         (before["cx"], before["cy"], before["fx"], before["fy"], before["inside"]))
        with connect() as conn:
            self.assertNotIn("town", movement, "nothing was walked or entered")

    def _door_plot(self):
        with connect() as conn:
            pos = tm.get_position(conn)
            chart = get_map(None, conn=conn)
            town = tg.stored_cell(conn, chart, pos["cx"], pos["cy"])
            plot = max((p for p in town["plots"] if p.get("k") == "shop" and p.get("f") and p.get("name")
                        and abs(p["f"][0] - pos["fx"]) + abs(p["f"][1] - pos["fy"]) <= 40),
                       key=lambda p: abs(p["f"][0] - pos["fx"]) + abs(p["f"][1] - pos["fy"]))
            tg.record_seen(conn, chart["id"], pos["cx"], pos["cy"], town["side"],
                           road_tiles=[plot["f"][1] * town["side"] + plot["f"][0]])
            know = tm._Knowledge(conn, chart, town)
        self.assertTrue(know.kind_known(plot))
        self.assertFalse(know.name_known(plot), "the probe needs a plot whose sign is unread")
        return plot

    def test_click_walk_hides_an_unread_sign(self):
        _apply(_plan("I look around."))
        plot = self._door_plot()
        with mock.patch.object(tm, "_record_walk_seen", lambda *a, **k: None), connect() as conn:
            walked = tm.click_walk(conn, plot_ref=plot["id"])
        self.assertEqual(walked["plan"]["target"]["name"], "")
        self.assertEqual(walked["report"].get("to"), "")
        self.assertNotIn(plot["name"], json.dumps(walked))

    def test_click_walk_names_the_plot_once_its_sign_is_read(self):
        _apply(_plan("I look around."))
        plot = self._door_plot()
        with connect() as conn:
            walked = tm.click_walk(conn, plot_ref=plot["id"])
        if walked["plan"].get("partial"):
            self.skipTest("the door is beyond one walk")
        self.assertEqual(walked["plan"]["target"]["name"], plot["name"])

    def test_click_walk_refuses_an_unseen_cell(self):
        _apply(_plan("I look around."))
        chart = get_map(None)
        here = tm.player_cell(chart)
        cells = tg._city_cells(self.city)
        other = next((c for c in cells if c != tuple(here)), None)
        if other is None:
            self.skipTest("a one-cell city")
        key = f"{other[0]},{other[1]}"
        chart["visited"] = [v for v in (chart.get("visited") or []) if str(v) != key]
        chart["revealed"] = [v for v in (chart.get("revealed") or []) if str(v) != key]
        with connect() as conn:
            _save_map_payload(chart, conn=conn)
            self.assertNotIn(key, tg._seen_world_cells(get_map(None, conn=conn)))
        made = _scalar("SELECT COUNT(*) FROM town_cells")
        with connect() as conn, self.assertRaises(ValueError):
            tm.click_walk(conn, cx=other[0], cy=other[1], fx=64, fy=64)
        self.assertEqual(_scalar("SELECT COUNT(*) FROM town_cells"), made, "an unseen cell is not generated")
        with self.assertRaises(main.HTTPException) as caught:
            main.api_town_walk(main.TownWalkRequest(cx=other[0], cy=other[1], fx=64, fy=64))
        self.assertEqual(caught.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
