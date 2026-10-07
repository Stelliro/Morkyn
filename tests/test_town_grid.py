"""
Town grid, slice A (docs/TownGrid.md): the generator, lazy storage, saves and the read API.

The player asked to zoom into a town and see its sub-grid, with roads to follow
and shops on the plots. Each city world cell already had a 128-max fine grid of
wards and a straight cross of avenues; app/town_grid.py lays a road network over
it, cuts plots, rolls shops by ward, and names them from the pools. These tests
hold the rules the design fixed before any of it was built.
"""
from __future__ import annotations

import copy
import json
import os
import random
import sys
import tempfile
import time
import unittest
from collections import deque
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-town-grid-"))
os.environ.update(isolated_data_env(str(_TMP)))

from fastapi import HTTPException  # noqa: E402

from app import main, town_grid as tg, world  # noqa: E402
from app.db import connect, init_db  # noqa: E402
from app.example_pools import _VENUE_CLOSED_WORDS  # noqa: E402
from app.local_intel import stamp_city_notices, stalls_for_district  # noqa: E402
from app.tile_world import generate_scaled_world, get_map, prune_world_maps  # noqa: E402
from app.venues import VENUE_KINDS, kind_for_era, venue_kind_from_name  # noqa: E402
from app.world_scale import build_city, cell_raster, street_mask, tiles_in_cell  # noqa: E402


def _world(seed: int, box: tuple[int, int] = (5, 5), *, band: str = "city", notices: int = 0,
           single_side: int | None = None, theme: str = "medieval") -> tuple[dict, dict]:
    city = build_city(random.Random(seed), origin=(1000, 1000), box_w=box[0], box_h=box[1],
                      single_side=single_side, slavery=False, city_id="C1", name="Ashford")
    city["band"] = band
    if notices:
        stamp_city_notices(city, notices, random.Random(seed + 1))
    chart = {"id": f"test-{seed}-{box[0]}x{box[1]}", "seed": seed * 7 + 1, "theme": theme, "cities": [city],
             "roads": [], "scale": "world"}
    return chart, city


def _centre(city: dict) -> dict:
    return max(city["cells"], key=lambda c: (int(c["side"]), -int(c["x"]), -int(c["y"])))


def _neighbour(city: dict, cell: dict) -> dict:
    cells = {(int(c["x"]), int(c["y"])): c for c in city["cells"]}
    for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1)):
        found = cells.get((int(cell["x"]) + dx, int(cell["y"]) + dy))
        if found:
            return found
    raise AssertionError("cell has no city neighbour")


def _names(town: dict) -> list[str]:
    return list(town["streets"]) + [p["name"] for p in town["plots"] if p.get("name") and p.get("vk")]


def _bfs_reached(roads, side: int, starts: list[int]) -> set[int]:
    reached = set(i for i in starts if roads[i])
    queue = deque(reached)
    while queue:
        i = queue.popleft()
        x, y = i % side, i // side
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < side and 0 <= ny < side:
                j = ny * side + nx
                if roads[j] and j not in reached:
                    reached.add(j)
                    queue.append(j)
    return reached


def _port_starts(chart, city, cell) -> list[int]:
    side = int(cell["side"])
    ports = tg.city_ports(chart, city)[(int(cell["x"]), int(cell["y"]))]
    return [tg.port_tile(p, side)[1] * side + tg.port_tile(p, side)[0] for p in ports]


_TEMPLE_SEED_CACHE: list[int] = []


def _temple_seed() -> int:
    """A fixed seed whose centre cell has a temple and a government ward."""
    if _TEMPLE_SEED_CACHE:
        return _TEMPLE_SEED_CACHE[0]
    for seed in range(1, 60):
        _chart, city = _world(seed)
        types = {d.get("type") for d in _centre(city)["districts"]}
        if {"temple", "government", "military", "shopping", "food", "craft"} <= types:
            _TEMPLE_SEED_CACHE.append(seed)
            return seed
    raise AssertionError("no seed with a temple ward")


class GeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.seed = _temple_seed()
        cls.chart, cls.city = _world(cls.seed, notices=60)
        cls.centre = _centre(cls.city)
        cls.town = tg.generate_cell(cls.chart, cls.city, cls.centre, "preindustrial")

    def test_same_inputs_give_byte_identical_rows(self):
        again = tg.generate_cell(self.chart, self.city, self.centre, "preindustrial")
        self.assertEqual(tg.encode_cell(again), tg.encode_cell(self.town))

    def test_generation_order_does_not_change_rows(self):
        a, b = self.centre, _neighbour(self.city, self.centre)
        a1 = tg.generate_cell(self.chart, self.city, a, "preindustrial")
        b1 = tg.generate_cell(self.chart, self.city, b, "preindustrial", used_names=_names(a1))
        b2 = tg.generate_cell(self.chart, self.city, b, "preindustrial")
        a2 = tg.generate_cell(self.chart, self.city, a, "preindustrial", used_names=_names(b2))
        self.assertEqual(tg.encode_cell(a1), tg.encode_cell(a2))
        self.assertEqual(tg.encode_cell(b1), tg.encode_cell(b2))

    def test_no_two_cells_can_hold_one_name(self):
        owners = tg.NameOwners(self.chart, self.city)
        here = (int(self.centre["x"]), int(self.centre["y"]))
        for name in _names(self.town):
            kind = "street_name" if name in self.town["streets"] else "venue_name"
            plot = next((p for p in self.town["plots"] if p.get("name") == name), None)
            if kind == "venue_name" and any(name.startswith(s + " ") for s in self.town["streets"]):
                continue  # "{street} {trade}": its street is this cell's own
            self.assertEqual(owners.owner(kind, name), here, (name, plot and plot.get("vk")))

    def test_a_name_collision_changes_only_that_name(self):
        taken = next(p for p in self.town["plots"] if p.get("vk") and p.get("name"))
        other = tg.generate_cell(self.chart, self.city, self.centre, "preindustrial", used_names=[taken["name"]])
        self.assertNotEqual(other["plots"][taken["n"]]["name"], taken["name"])
        for mine, theirs in zip(self.town["plots"], other["plots"]):
            if mine["n"] == taken["n"]:
                continue
            self.assertEqual(mine, theirs)
        self.assertEqual(bytes(other["roads"]), bytes(self.town["roads"]))
        self.assertEqual(other["streets"], self.town["streets"])

    def test_city_ports_read_no_fine_grid(self):
        tg.clear_caches()
        with mock.patch.object(tg, "street_mask", side_effect=AssertionError("fine grid read")), \
                mock.patch.object(tg, "_skeleton_roads", side_effect=AssertionError("fine grid read")):
            ports = tg.city_ports(self.chart, self.city)
        self.assertEqual(set(ports), {(int(c["x"]), int(c["y"])) for c in self.city["cells"]})
        big_chart, big_city = _world(3, (9, 9))
        tg.clear_caches()
        start = time.perf_counter()
        tg.city_ports(big_chart, big_city)
        self.assertLess(time.perf_counter() - start, 0.05)

    def test_shared_edges_agree_on_t(self):
        ports = tg.city_ports(self.chart, self.city)
        for pos, items in ports.items():
            for port in items:
                if port["to"] is None:
                    continue
                back = [p for p in ports[tuple(port["to"])] if p["to"] == [pos[0], pos[1]]]
                self.assertIn(port["t"], [p["t"] for p in back])

    def test_legacy_avenues_and_wards_are_unchanged(self):
        cell = self.centre
        before = (copy.deepcopy(cell), cell_raster(cell, 16), tiles_in_cell(cell))
        town = tg.generate_cell(self.chart, self.city, cell, "preindustrial")
        side = int(cell["side"])
        for x, y in street_mask(int(cell["seed"]), side):
            self.assertEqual(town["roads"][y * side + x], tg.ROAD_AVENUE)
        self.assertEqual(cell, before[0])
        self.assertEqual(cell_raster(cell, 16), before[1])
        self.assertEqual(tiles_in_cell(cell), before[2])

    def test_every_road_tile_and_port_is_reachable(self):
        for cell in self.city["cells"][:8] + [self.centre]:
            with self.subTest(cell=(cell["x"], cell["y"], cell["side"])):
                town = tg.generate_cell(self.chart, self.city, cell, "preindustrial")
                side = town["side"]
                starts = _port_starts(self.chart, self.city, cell)
                for i in starts:
                    self.assertTrue(town["roads"][i], "a port is off the road")
                reached = _bfs_reached(town["roads"], side, starts)
                self.assertEqual(reached, {i for i in range(side * side) if town["roads"][i]})

    def test_plots_do_not_overlap_or_sit_on_roads(self):
        town, side = self.town, self.town["side"]
        owner = {}
        for plot in town["plots"]:
            x, y, w, h = plot["r"]
            self.assertGreater(w * h, 0)
            for yy in range(y, y + h):
                for xx in range(x, x + w):
                    i = yy * side + xx
                    self.assertNotIn(i, owner, f"plots {owner.get(i)} and {plot['n']} overlap")
                    self.assertFalse(town["roads"][i], "a plot covers a road tile")
                    owner[i] = plot["n"]
            if plot["k"] == "yard":
                continue
            fx, fy = plot["f"]
            self.assertTrue(town["roads"][fy * side + fx], "frontage is not a road tile")
            beside = (x - 1 <= fx <= x + w and y <= fy < y + h and fx in (x - 1, x + w)) or \
                (y - 1 <= fy <= y + h and x <= fx < x + w and fy in (y - 1, y + h))
            self.assertTrue(beside, f"frontage {plot['f']} not orthogonally beside {plot['r']}")

    def test_landmarks_stand_at_temple_and_government_anchors(self):
        districts = self.centre["districts"]
        for index, district in enumerate(districts):
            kind = {"temple": "temple", "government": "office"}.get(district["type"])
            if not kind:
                continue
            with self.subTest(ward=district["type"]):
                marks = [p for p in self.town["plots"] if p["k"] == kind and "anchor" in (p.get("fl") or []) and p["d"] == index]
                self.assertEqual(len(marks), 1)
                x, y, w, h = marks[0]["r"]
                ax, ay = district["anchor"]
                self.assertLessEqual(max(abs(ax - (x + w // 2)), abs(ay - (y + h // 2))), max(w, h))

    def test_every_venue_kind_has_a_weight_row(self):
        self.assertEqual(set(VENUE_KINDS) - set(tg.KIND_WEIGHTS), set())

    def test_skeleton_is_the_stored_main_network(self):
        tg.clear_caches()
        sk = tg.skeleton(self.chart, self.city, self.centre)
        stored = bytes(c if c in (tg.ROAD_AVENUE, tg.ROAD_MAIN) else 0 for c in self.town["roads"])
        self.assertEqual(bytes(sk["roads"]), stored)

    def test_era_decides_the_trades(self):
        modern = tg.generate_cell(self.chart, self.city, self.centre, "modern")
        old = self.town
        self.assertFalse({p.get("vk") for p in modern["plots"]} & {"smithy", "alchemist"})
        self.assertFalse({p.get("vk") for p in old["plots"]} & {"garage", "diner", "bar"})
        self.assertTrue({p.get("vk") for p in modern["plots"]} & {"garage", "diner", "bar"})

    def test_budget_for_a_128_cell(self):
        self.assertEqual(self.centre["side"], 128)
        start = time.perf_counter()
        town = tg.generate_cell(self.chart, self.city, self.centre, "preindustrial")
        self.assertLess(time.perf_counter() - start, 1.0)
        size = sum(len(v) for v in tg.encode_cell(town).values() if isinstance(v, str))
        self.assertLess(size, 96 * 1024)


class NameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.chart, cls.city = _world(_temple_seed())
        used: list[str] = []
        cls.towns = []
        centre = _centre(cls.city)
        for cell in [centre, _neighbour(cls.city, centre)] + cls.city["cells"][:3]:
            if any(t["cx"] == cell["x"] and t["cy"] == cell["y"] for t in cls.towns):
                continue
            town = tg.generate_cell(cls.chart, cls.city, cell, "preindustrial", used_names=used)
            used.extend(_names(town))
            cls.towns.append(town)

    def test_names_are_unique_in_the_city(self):
        names = [n.lower() for t in self.towns for n in _names(t)]
        self.assertEqual(len(names), len(set(names)))

    def test_every_plot_name_reads_as_its_kind(self):
        street_forms = 0
        for town in self.towns:
            for plot in town["plots"]:
                if not plot.get("vk"):
                    continue
                name = plot["name"]
                found = venue_kind_from_name(name)
                with self.subTest(name=name, vk=plot["vk"]):
                    if found != plot["vk"]:
                        self.assertIn(plot["vk"], ("inn", "tavern", "bar"))
                        self.assertEqual(found, "")
                    self.assertNotIn(name.split()[-1].lower(), _VENUE_CLOSED_WORDS)
                seg = plot.get("seg")
                if seg is not None and town["segments"][seg].get("name_id") is not None:
                    street = town["streets"][town["segments"][seg]["name_id"]]
                    if name.startswith(street + " "):
                        street_forms += 1
                        self.assertEqual(found, plot["vk"])
        self.assertGreater(street_forms, 0, "no {street} form was drawn")

    def test_streets_never_read_as_venues(self):
        for town in self.towns:
            for street in town["streets"]:
                self.assertEqual(venue_kind_from_name(street), "", street)


class ShopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.samples = []
        for seed in (_temple_seed(), 11, 23):
            chart, city = _world(seed)
            centre = _centre(city)
            cells = [centre] + [c for c in city["cells"] if c is not centre][:4]
            for cell in cells:
                cls.samples.append((chart, city, cell, tg.generate_cell(chart, city, cell, "preindustrial")))

    def test_every_stall_is_a_shop_in_its_own_district(self):
        wrapped = 0
        for chart, city, cell, town in self.samples:
            by_stall = {p["st"]: p for p in town["plots"] if p.get("st")}
            for index, district in enumerate(cell["districts"]):
                stalls = stalls_for_district(cell, district, theme="medieval", slavery=False)
                for number, stall in enumerate(stalls):
                    if stall["filler"]:
                        continue
                    plot = by_stall.get(f"{district['id']}:{number}")
                    with self.subTest(cell=(cell["x"], cell["y"]), stall=number, district=district["id"]):
                        self.assertIsNotNone(plot, "a stall local_intel told players about has no plot")
                        self.assertEqual(plot["d"], index)
                        self.assertIn(plot["k"], ("shop", "service"))
                        self.assertNotIn(plot["k"], ("temple", "office", "barracks", "gate"))
                        good = stall["good"]
                        row = tg.STALL_GOOD_KINDS.get(good) or tg._FENCE_KINDS
                        fitted = {kind_for_era(k, "preindustrial") for k in row} | set(tg._FENCE_KINDS)
                        self.assertIn(plot["vk"], fitted)
                    if stall["fine_x"] < district["anchor"][0] + 2 or stall["fine_y"] < district["anchor"][1] + 1:
                        wrapped += 1
        self.assertGreater(wrapped, 0, "the sample has no stall whose position wraps across the cell")

    def test_shop_share_follows_the_ward(self):
        rows: dict[str, list[int]] = {}
        for _chart, _city, cell, town in self.samples:
            for plot in town["plots"]:
                if plot.get("f") is None or plot["k"] == "gate" or "anchor" in (plot.get("fl") or []):
                    continue
                kind = cell["districts"][plot["d"]]["type"]
                row = rows.setdefault(kind, [0, 0])
                row[0] += 1
                row[1] += plot["k"] in ("shop", "service")
        share = {kind: hits / total for kind, (total, hits) in rows.items() if total}
        self.assertGreater(share["shopping"], 0.4)
        self.assertGreater(share["shopping"], share["food"])
        self.assertGreater(share["shopping"], share["craft"])
        self.assertGreater(min(share["food"], share["craft"]), share["residential"])
        self.assertGreater(share["residential"], max(share["temple"], share["government"]))

    def test_kind_caps_hold_per_district(self):
        for _chart, _city, cell, town in self.samples:
            front: dict[int, int] = {}
            for plot in town["plots"]:
                if plot.get("f") is None or plot["k"] == "gate" or "anchor" in (plot.get("fl") or []):
                    continue
                front[plot["d"]] = front.get(plot["d"], 0) + 1
            counts: dict[tuple[int, str], int] = {}
            for plot in town["plots"]:
                if plot.get("vk") and not ({"stall", "guild"} & set(plot.get("fl") or [])) and plot["k"] != "temple":
                    counts[(plot["d"], plot["vk"])] = counts.get((plot["d"], plot["vk"]), 0) + 1
            for (d, kind), count in counts.items():
                density = int(cell["districts"][d].get("density") or 0)
                self.assertLessEqual(count, tg.kind_cap(kind, front.get(d, 0), density), (d, kind))

    def test_capped_rolls_fall_through_to_the_ward_row(self):
        chart, city, cell, _town = self.samples[0]
        with mock.patch.object(tg, "kind_cap", return_value=0):
            town = tg.generate_cell(chart, city, cell, "preindustrial")
        for plot in town["plots"]:
            if plot.get("f") is None or plot["k"] == "gate" or "anchor" in (plot.get("fl") or []):
                continue
            if {"stall", "guild"} & set(plot.get("fl") or []):
                continue
            ward = cell["districts"][plot["d"]]["type"]
            allowed = {kind for kind, _w in tg.OTHERWISE.get(ward, tg.OTHERWISE["residential"])} | {"empty"}
            self.assertIn(plot["k"], allowed)
            self.assertFalse(plot.get("vk"))


class NoticeTests(unittest.TestCase):
    def test_far_notice_lands_in_its_destination_cell(self):
        chart, city = _world(_temple_seed())
        a = _centre(city)
        b = _neighbour(city, a)
        for cell in city["cells"]:
            cell["notices"] = []
        far = {"id": "C1:far:0", "kind": "guild", "label": "Guild hall", "x": b["x"], "y": b["y"],
               "fine_x": 5, "fine_y": 5, "far": True, "home_x": a["x"], "home_y": a["y"]}
        a["notices"] = [far]
        tg.clear_caches()
        a1 = tg.generate_cell(chart, city, a, "preindustrial")
        b1 = tg.generate_cell(chart, city, b, "preindustrial", used_names=_names(a1))
        self.assertFalse([p for p in a1["plots"] if p.get("nt")])
        holders = [p for p in b1["plots"] if "C1:far:0" in (p.get("nt") or [])]
        self.assertEqual(len(holders), 1)
        self.assertEqual(holders[0].get("vk"), "guild_hall")
        b2 = tg.generate_cell(chart, city, b, "preindustrial")
        a2 = tg.generate_cell(chart, city, a, "preindustrial", used_names=_names(b2))
        self.assertEqual(tg.encode_cell(a1), tg.encode_cell(a2))
        self.assertEqual(tg.encode_cell(b1), tg.encode_cell(b2))


class FullCityTests(unittest.TestCase):
    """A whole 9 x 9 box city, generated cell by cell (test only; the game never does this)."""

    def test_the_network_joins_through_every_port(self):
        chart, city = _world(5, (9, 9), band="metropolis")
        ports = tg.city_ports(chart, city)
        towns = {}
        for cell in city["cells"]:
            towns[(int(cell["x"]), int(cell["y"]))] = tg.generate_cell(chart, city, cell, "preindustrial")
        parent = {pos: pos for pos in towns}

        def find(p):
            while parent[p] != p:
                parent[p] = parent[parent[p]]
                p = parent[p]
            return p

        for pos, items in ports.items():
            side = towns[pos]["side"]
            for port in items:
                x, y = tg.port_tile(port, side)
                self.assertTrue(towns[pos]["roads"][y * side + x], f"port off road in {pos}")
                if port["to"] is not None:
                    other = tuple(port["to"])
                    oside = towns[other]["side"]
                    back = next(p for p in ports[other] if p["to"] == [pos[0], pos[1]] and p["t"] == port["t"])
                    ox, oy = tg.port_tile(back, oside)
                    self.assertTrue(towns[other]["roads"][oy * oside + ox])
                    parent[find(pos)] = find(other)
        self.assertEqual(len({find(p) for p in towns}), 1)
        self.assertTrue(any(p.get("gate") for items in ports.values() for p in items))


class StorageAndApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        generate_scaled_world(preset_id="forest_march", seed=20261007, density_percent=60, notice_percent=40)
        cls.chart = get_map(None)
        px, py = int(cls.chart["player"]["x"]), int(cls.chart["player"]["y"])
        cls.here = (px, py)
        cls.city = tg._locate(cls.chart, px, py)[0]

    def setUp(self):
        with connect() as conn:
            conn.execute("DELETE FROM town_cells")
            conn.execute("DELETE FROM town_seen")
        tg.clear_caches()

    def _count(self, conn) -> int:
        return int(conn.execute("SELECT COUNT(*) FROM town_cells").fetchone()[0])

    def test_get_cell_is_lazy_and_cached(self):
        with connect() as conn:
            self.assertIsNone(tg.get_cell(conn, self.chart, *self.here))
            self.assertEqual(self._count(conn), 0)
            town = tg.get_cell(conn, self.chart, *self.here, create=True)
            self.assertEqual(self._count(conn), 1)
            self.assertTrue(town["plots"])
            with mock.patch.object(tg, "generate_cell", side_effect=AssertionError("regenerated")):
                again = tg.get_cell(conn, self.chart, *self.here, create=True)
            self.assertEqual(again["plots"], town["plots"])
            self.assertEqual(self._count(conn), 1)

    def test_an_older_gen_version_row_is_kept(self):
        with connect() as conn:
            town = tg.get_cell(conn, self.chart, *self.here, create=True)
            conn.execute("UPDATE town_cells SET gen_version = 0")
            with mock.patch.object(tg, "generate_cell", side_effect=AssertionError("regenerated")):
                kept = tg.get_cell(conn, self.chart, *self.here, create=True)
        self.assertEqual(kept["gen_version"], 0)
        self.assertEqual(kept["plots"], town["plots"])

    def test_view_shows_only_what_was_seen(self):
        with connect() as conn:
            town = tg.get_cell(conn, self.chart, *self.here, create=True)
            view = tg.town_view(conn, self.chart, r=0)
            cell = view["cells"][0]
            self.assertTrue(cell["generated"])
            self.assertEqual({p["k"] for p in cell["plots"]} - {"gate"}, set())
            roads = tg._unpack(cell["roads"])
            self.assertEqual(set(roads) - {0, tg.ROAD_AVENUE, tg.ROAD_MAIN}, set())
            shop = next(p for p in town["plots"] if p.get("k") == "shop")
            side = town["side"]
            fx, fy = shop["f"]
            tg.record_seen(conn, self.chart["id"], *self.here, side, road_tiles=[fy * side + fx])
            view = tg.town_view(conn, self.chart, r=0)
            seen = {p["id"]: p for p in view["cells"][0]["plots"]}
            self.assertIn(shop["id"], seen)
            self.assertNotIn("name", seen[shop["id"]], "a sign is read only from close by")
            tg.record_seen(conn, self.chart["id"], *self.here, side, plot_ns=[shop["n"]])
            view = tg.town_view(conn, self.chart, r=0)
            seen = {p["id"]: p for p in view["cells"][0]["plots"]}
            self.assertEqual(seen[shop["id"]]["name"], shop["name"])
            self.assertIn("open", seen[shop["id"]])
            peek = tg.plot_peek(conn, self.chart, shop["id"])
            self.assertEqual(peek["name"], shop["name"])

    def test_record_seen_appends_only_new_bits(self):
        with connect() as conn:
            town = tg.get_cell(conn, self.chart, *self.here, create=True)
            side = town["side"]
            self.assertIsNotNone(tg.record_seen(conn, self.chart["id"], *self.here, side, road_tiles=[1, 2], plot_ns=[3]))
            self.assertIsNone(tg.record_seen(conn, self.chart["id"], *self.here, side, road_tiles=[2], plot_ns=[3]))
            self.assertIsNotNone(tg.record_seen(conn, self.chart["id"], *self.here, side, told=["stall:d0:0"]))
            folded = tg.fold_seen(conn, self.chart["id"], *self.here, side, len(town["plots"]))
            self.assertTrue(tg._bit(folded["roads"], 1) and tg._bit(folded["roads"], 2))
            self.assertTrue(tg._bit(folded["plots"], 3))
            self.assertEqual(folded["told"], ["stall:d0:0"])

    def test_a_seen_ungenerated_cell_shows_its_skeleton_and_writes_nothing(self):
        chart = copy.deepcopy(self.chart)
        cells = {(int(c["x"]), int(c["y"])) for c in self.city["cells"]}
        others = sorted(cells - {self.here})
        self.assertTrue(others, "the start city needs more than one cell for this test")
        chart["visited"] = list(chart.get("visited") or []) + [f"{x},{y}" for x, y in others]
        with connect() as conn:
            before = self._count(conn)
            view = tg.town_view(conn, chart, r=1)
            self.assertEqual(self._count(conn), before)
            self.assertEqual(int(conn.execute("SELECT COUNT(*) FROM town_seen").fetchone()[0]), 0)
        known = [c for c in view["cells"] if c.get("known")]
        self.assertTrue(known)
        for cell in known:
            self.assertFalse(cell["generated"])
            self.assertEqual(cell["plots"], [])
            roads = tg._unpack(cell["roads"])
            self.assertEqual(set(roads) - {0, tg.ROAD_AVENUE, tg.ROAD_MAIN}, set())
            self.assertTrue(any(roads))

    def test_wide_views_are_refused(self):
        with connect() as conn:
            with self.assertRaises(ValueError):
                tg.town_view(conn, self.chart, r=2)
        with self.assertRaises(HTTPException) as caught:
            main.api_town_view(r=2)
        self.assertEqual(caught.exception.status_code, 400)

    def test_legacy_map_and_unknown_plot(self):
        with connect() as conn:
            self.assertFalse(tg.town_view(conn, {"scale": "legacy", "cities": []})["available"])
        with self.assertRaises(HTTPException) as caught:
            main.api_town_plot(f"{self.city['id']}.0.0.99999")
        self.assertEqual(caught.exception.status_code, 404)

    def test_a_hamlet_works(self):
        chart = copy.deepcopy(self.chart)
        hamlet = min(chart["cities"], key=lambda c: (int(c["footprint"]), max(int(x["side"]) for x in c["cells"])))
        cell = hamlet["cells"][0]
        chart["visited"] = list(chart.get("visited") or []) + [f"{cell['x']},{cell['y']}"]
        with connect() as conn:
            town = tg.get_cell(conn, chart, int(cell["x"]), int(cell["y"]), create=True)
            self.assertTrue(town["plots"])
            self.assertTrue(any(p["k"] == "gate" for p in town["plots"]))
            view = tg.town_view(conn, chart, city_id=hamlet["id"], r=0)
        self.assertTrue(view["available"])
        self.assertTrue(view["cells"][0]["generated"])

    def test_settlement_route_says_it_can_zoom(self):
        out = main.api_tile_settlement()
        self.assertTrue(out["town"]["zoomable"])
        self.assertIsNone(out["town"]["player"])
        with connect() as conn:
            self.assertEqual(self._count(conn), 0, "GET must not generate")

    def test_route_view_never_generates(self):
        out = main.api_town_view()
        self.assertTrue(out["available"])
        with connect() as conn:
            self.assertEqual(self._count(conn), 0)


class SaveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        generate_scaled_world(preset_id="forest_march", seed=777, density_percent=50, notice_percent=30)
        cls.chart = get_map(None)
        cls.here = (int(cls.chart["player"]["x"]), int(cls.chart["player"]["y"]))

    def _walk_town(self, conn) -> None:
        town = tg.get_cell(conn, self.chart, *self.here, create=True)
        tg.record_seen(conn, self.chart["id"], *self.here, town["side"], road_tiles=[0, 1, 2], plot_ns=[0])

    def test_tables_are_ordinary_world_tables(self):
        for table in ("town_cells", "town_seen"):
            self.assertIn(table, world.WORLD_TABLES)
            self.assertIn(table, world.RESTORE_ORDER)
            self.assertNotIn(table, world._REPLACE_ONLY_WHEN_EXPORTED)
        self.assertIn("town_seen", world.AUTOINC_TABLES)
        with connect() as conn:
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(locations)").fetchall()}
            self.assertTrue({"plot_id", "city_id"} <= cols)
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(npcs)").fetchall()}
            self.assertIn("workplace_plot", cols)

    def test_export_carries_only_the_campaign_map(self):
        with connect() as conn:
            conn.execute("DELETE FROM town_cells")
            self._walk_town(conn)
            conn.execute(
                "INSERT INTO town_cells (map_id, cx, cy, city_id, gen_version, port_version, side, era, roads, segments, streets, plots) "
                "SELECT 'stale-map', cx, cy, city_id, gen_version, port_version, side, era, roads, segments, streets, plots FROM town_cells"
            )
            conn.execute("INSERT INTO town_seen (map_id, cx, cy) VALUES ('stale-map', 1, 1)")
        payload = world.export_world()
        self.assertEqual({r["map_id"] for r in payload["tables"]["town_cells"]}, {self.chart["id"]})
        self.assertEqual({r["map_id"] for r in payload["tables"]["town_seen"]}, {self.chart["id"]})
        with connect() as conn:
            prune_world_maps(conn)
            maps = {r[0] for r in conn.execute("SELECT DISTINCT map_id FROM town_cells").fetchall()}
            seen_maps = {r[0] for r in conn.execute("SELECT DISTINCT map_id FROM town_seen").fetchall()}
        self.assertEqual(maps, {self.chart["id"]})
        self.assertEqual(seen_maps, {self.chart["id"]})

    def test_round_trip_and_old_save(self):
        with connect() as conn:
            conn.execute("DELETE FROM town_cells")
            conn.execute("DELETE FROM town_seen")
            self._walk_town(conn)
        payload = json.loads(json.dumps(world.export_world()))
        self.assertEqual(len(payload["tables"]["town_cells"]), 1)
        world._restore_world(payload)
        tg.clear_caches()
        with connect() as conn:
            self.assertEqual(int(conn.execute("SELECT COUNT(*) FROM town_cells").fetchone()[0]), 1)
            self.assertEqual(int(conn.execute("SELECT COUNT(*) FROM town_seen").fetchone()[0]), 1)
            self.assertIsNotNone(tg.get_cell(conn, self.chart, *self.here))
        old = json.loads(json.dumps(payload))
        old["tables"].pop("town_cells")
        old["tables"].pop("town_seen")
        world._restore_world(old)
        with connect() as conn:
            self.assertEqual(int(conn.execute("SELECT COUNT(*) FROM town_cells").fetchone()[0]), 0)
            self.assertEqual(int(conn.execute("SELECT COUNT(*) FROM town_seen").fetchone()[0]), 0)
            self.assertIsNone(tg.get_cell(conn, self.chart, *self.here), "a stale cache row was served")

    def test_new_playthrough_drops_town_rows(self):
        with connect() as conn:
            self._walk_town(conn)
            world._clear_playthrough(conn)
            self.assertEqual(int(conn.execute("SELECT COUNT(*) FROM town_cells").fetchone()[0]), 0)
            self.assertEqual(int(conn.execute("SELECT COUNT(*) FROM town_seen").fetchone()[0]), 0)


if __name__ == "__main__":
    unittest.main()
