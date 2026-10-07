"""
Town grid: roads, plots and plotted shops inside a city's world cells.

docs/TownGrid.md, slice A. A city is a clump of world cells (app/world_scale.py),
each with a ``side x side`` fine grid that always covers exactly one world
cell. Until now that grid held wards and a straight cross of avenues and
nothing else, so a shop existed only once the prose named one. This module
gives every city cell a real road network and cuts its blocks into plots,
some of which are shops, by the rules the districts already carry
(``density``, ``shop_count``, the stalls ``local_intel`` has told players about).

What it holds to:

  * **Pure and deterministic.** ``generate_cell`` reads the world record and
    nothing else. Every stage draws from its own ``random.Random`` salted by
    the world seed and the cell, so a change to naming never moves a road.
  * **Lazy per cell.** Nothing builds a whole city. ``get_cell(create=True)``
    generates one cell and stores it in ``town_cells``; joins between cells
    come from ``city_ports``, computed from the city record alone.
  * **Stored rows are the authority.** Once generated, a cell is never
    regenerated, even under a newer ``GEN_VERSION``: a player who read a sign
    must find the same name there.
  * **Reads never write.** ``town_view`` and ``plot_peek`` use stored rows and
    in-memory skeletons (stages 1 and 2) for seen cells that were never
    generated, and they never call the generator.
  * **No model calls.** Names come from ``example_pools`` draws.
"""
from __future__ import annotations

import base64
import json
import random
import threading
import zlib
from collections import OrderedDict, deque
from typing import Any, Iterable

from app.world_scale import CITY_CELL_MAX, clamp_int, mix_hash, normalize_density, street_mask

# 2: roads meet across a city's shared cell edges (edge_joins, playtest #70)
# and plots fill from one town centre (town_field, playtest #72). Stored v1
# rows stay as they are; a v2 cell next to one meets the roads it already has.
GEN_VERSION = 2
# Frozen once shipped: changing where ports sit would disconnect cells a save
# already generated from cells it generates later (TownGrid.md 3.1, 3.5).
PORT_VERSION = 1

CELL_METRES = 800
TOWN_LOOKUP_CELLS = 2
MAX_VIEW_RADIUS = 1
CELL_LRU_SIZE = 9
SKELETON_LRU_SIZE = 27
PORTS_LRU_SIZE = 16

ROAD_NONE = 0
ROAD_AVENUE = 1
ROAD_MAIN = 2
ROAD_STREET = 3
ROAD_ALLEY = 4
ROAD_CLASS_NAMES = {ROAD_AVENUE: "avenue", ROAD_MAIN: "main", ROAD_STREET: "street", ROAD_ALLEY: "alley"}

# One salt per stage, so each stage's rolls are independent of the others.
_SALT_PORT = 7101
_SALT_MAIN = 7102
_SALT_SIDE = 7103
_SALT_ALLEY = 7104
_SALT_PLOTS = 7106
_SALT_ROLLS = 7107
_SALT_NAMES = 7108
_SALT_STREETS = 7109
_SALT_GATE = 7110
_SALT_WALLS = 7111
_SALT_RURAL = 7112

_EDGE_COMPASS = {"N": "north", "E": "east", "S": "south", "W": "west"}
_EDGE_STEP = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}
_NEIGHBOURS = ((0, -1), (1, 0), (0, 1), (-1, 0))

LANDMARK_KINDS = frozenset({"temple", "office", "barracks"})
_NOT_STALL_TARGETS = LANDMARK_KINDS | {"gate"}

# Ward geometry in metres: block length, plot frontage, plot depth, and the
# density from which deep blocks get an alley (None: never, 0: always).
WARD_SPECS: dict[str, dict[str, Any]] = {
    "shopping":     {"block": (45, 65),   "front": (6, 12),  "depth": (12, 20), "alley": 55},
    "food":         {"block": (55, 75),   "front": (8, 14),  "depth": (14, 22), "alley": 60},
    "craft":        {"block": (65, 85),   "front": (10, 20), "depth": (16, 26), "alley": 60},
    "black_market": {"block": (35, 55),   "front": (6, 10),  "depth": (10, 16), "alley": 0},
    "residential":  {"block": (75, 105),  "front": (8, 16),  "depth": (16, 28), "alley": 70},
    "temple":       {"block": (120, 160), "front": (12, 24), "depth": (16, 30), "alley": None},
    "government":   {"block": (110, 150), "front": (12, 24), "depth": (16, 30), "alley": None},
    "military":     {"block": (110, 150), "front": (20, 40), "depth": (20, 40), "alley": None},
}
_DEFAULT_WARD = WARD_SPECS["residential"]
LANDMARK_METRES = 60
SIDE_STREET_PASSES = 4
GATE_METRES = 12

# Shop chance per frontage plot before caps, and what a plot is otherwise.
SHOP_BASE: dict[str, float] = {
    "shopping": 0.55, "food": 0.45, "craft": 0.40, "black_market": 0.35,
    "residential": 0.04, "military": 0.02, "government": 0.02, "temple": 0.02,
}
OTHERWISE: dict[str, tuple[tuple[str, float], ...]] = {
    "shopping": (("house", 0.35), ("warehouse", 0.10)),
    "food": (("warehouse", 0.30), ("house", 0.25)),
    "craft": (("yard", 0.30), ("house", 0.30)),
    "black_market": (("house", 0.40), ("empty", 0.25)),
    "residential": (("house", 0.85), ("yard", 0.10)),
    "military": (("barracks", 0.40), ("warehouse", 0.30), ("yard", 0.30)),
    "government": (("office", 0.60), ("house", 0.40)),
    "temple": (("house", 0.50), ("yard", 0.50)),
}

# The thin outer fringe of a town, where the setting farms its edge (playtest
# #72): what an otherwise-roll becomes there. These are not named kinds, so
# they never enter places_here or the prompt.
RURAL_KINDS: tuple[tuple[str, float], ...] = (("field", 0.35), ("pasture", 0.25), ("orchard", 0.15), ("yard", 0.25))
FRINGE_CORE = 0.2
_NO_RURAL_THEMES = frozenset({"space_opera", "far_future"})

# Kinds that are not retail: a shop roll that lands on one is a service plot.
SERVICE_KINDS = frozenset({
    "inn", "tavern", "bar", "bathhouse", "stable", "clinic", "shrine", "well", "guild_hall", "guardhouse",
})

# Kind weights by ward type (weights, not names). Every key of
# venues.VENUE_KINDS has a row; a test holds that. "temple" is a landmark
# kind and never rolled.
KIND_WEIGHTS: dict[str, dict[str, int]] = {
    "shrine":         {"temple": 4, "residential": 2, "food": 1},
    "well":           {"residential": 2, "food": 1},
    "inn":            {"shopping": 3, "food": 4, "craft": 1},
    "tavern":         {"food": 5, "shopping": 2, "craft": 2, "residential": 2, "black_market": 4, "military": 2},
    "smithy":         {"craft": 6, "military": 3, "shopping": 1},
    "general_store":  {"shopping": 6, "food": 2, "residential": 6, "craft": 1, "black_market": 4},
    "mill":           {"food": 2, "craft": 1},
    "stable":         {"food": 1, "craft": 1, "military": 2, "residential": 1},
    "bakery":         {"food": 6, "shopping": 2, "residential": 3},
    "apothecary":     {"shopping": 3, "temple": 2, "residential": 1, "black_market": 2},
    "butcher":        {"food": 5, "shopping": 1},
    "tailor":         {"shopping": 4, "craft": 3},
    "tanner":         {"craft": 3},
    "carpenter":      {"craft": 5, "residential": 1},
    "scribe":         {"government": 4, "shopping": 2, "temple": 1},
    "temple":         {},
    "guardhouse":     {"military": 5, "government": 3},
    "market_hall":    {"shopping": 2, "food": 2},
    "bathhouse":      {"shopping": 1, "residential": 1, "temple": 1, "food": 1},
    "armorer":        {"craft": 3, "military": 4, "shopping": 1},
    "jeweller":       {"shopping": 3, "craft": 2},
    "alchemist":      {"shopping": 2, "craft": 1, "black_market": 2},
    "library":        {"government": 2, "temple": 2, "shopping": 1},
    "guild_hall":     {"craft": 2, "shopping": 1},
    "counting_house": {"shopping": 2, "government": 2},
    "garage":         {"craft": 6, "military": 2, "residential": 1, "shopping": 1},
    "salvage_yard":   {"craft": 3, "black_market": 3},
    "clinic":         {"residential": 2, "temple": 1, "government": 1, "military": 1, "shopping": 1},
    "pharmacy":       {"shopping": 3, "residential": 2},
    "diner":          {"food": 6, "shopping": 3, "residential": 2, "craft": 1},
    "bar":            {"food": 4, "shopping": 2, "residential": 2, "black_market": 4, "craft": 1},
    "laundromat":     {"residential": 3, "shopping": 1},
}

# A stall's good -> the venue kinds that sell it (era-fitted at use).
STALL_GOOD_KINDS: dict[str, tuple[str, ...]] = {
    "food": ("bakery", "butcher", "general_store", "diner"),
    "weapons": ("smithy", "armorer"),
    "tools": ("smithy", "carpenter", "garage"),
    "cloth": ("tailor",),
    "books": ("scribe", "library"),
    "magic": ("alchemist", "apothecary"),
    "general": ("general_store",),
    "games": ("general_store",),
}
_FENCE_KINDS = ("general_store", "tavern", "bar")
_FENCE_GOODS = frozenset({"drugs", "songs", "slavery", "contraband", "black_market"})

_BAND_SIZE = {
    "hamlet": "hamlet", "village": "village", "town": "town",
    "city": "city", "large_city": "city", "metropolis": "city",
}


# ---------------------------------------------------------------------------
# Scale
# ---------------------------------------------------------------------------


def cell_cross_minutes() -> int:
    """Minutes to cross one city world cell on foot, read from the world walk table."""
    try:
        from app.tile_world import TERRAIN_WALK_MINUTES

        return int(TERRAIN_WALK_MINUTES.get("city", 10))
    except Exception:
        return 10


def town_walk_budget() -> int:
    try:
        from app.tile_world import STEP_BUDGET
    except Exception:
        STEP_BUDGET = 4
    return int(STEP_BUDGET) * cell_cross_minutes()


def tile_metres(side: int) -> float:
    return CELL_METRES / max(1, int(side))


def tile_minutes(side: int) -> float:
    return cell_cross_minutes() / max(1, int(side))


def metres_to_tiles(metres: float, side: int) -> int:
    return max(1, int(round(float(metres) / tile_metres(side))))


def settlement_size_for_band(band: str) -> str:
    return _BAND_SIZE.get(str(band or ""), "village")


def _ward_spec(kind: str) -> dict[str, Any]:
    return WARD_SPECS.get(str(kind or ""), _DEFAULT_WARD)


# ---------------------------------------------------------------------------
# Small LRU caches (per process)
# ---------------------------------------------------------------------------


class _LRU:
    def __init__(self, size: int) -> None:
        self.size = size
        self._data: OrderedDict = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            if key not in self._data:
                return None
            self._data.move_to_end(key)
            return self._data[key]

    def put(self, key, value) -> None:
        with self._lock:
            self._data[key] = value
            self._data.move_to_end(key)
            while len(self._data) > self.size:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


_CELL_CACHE = _LRU(CELL_LRU_SIZE)
_SKELETON_CACHE = _LRU(SKELETON_LRU_SIZE)
_PORTS_CACHE = _LRU(PORTS_LRU_SIZE)
_JOINS_CACHE = _LRU(PORTS_LRU_SIZE)


def clear_caches() -> None:
    _CELL_CACHE.clear()
    _SKELETON_CACHE.clear()
    _PORTS_CACHE.clear()
    _JOINS_CACHE.clear()


# ---------------------------------------------------------------------------
# Ports (TownGrid.md 3.1): city level, no fine grid
# ---------------------------------------------------------------------------


def _cell_key(x: int, y: int) -> int:
    return ((int(x) & 0xFFFF) << 16) | (int(y) & 0xFFFF)


def _city_cells(city: dict[str, Any]) -> dict[tuple[int, int], dict[str, Any]]:
    out: dict[tuple[int, int], dict[str, Any]] = {}
    for cell in city.get("cells") or []:
        if isinstance(cell, dict):
            out[(int(cell.get("x") or 0), int(cell.get("y") or 0))] = cell
    return out


def _side(cell: dict[str, Any]) -> int:
    return clamp_int(int(cell.get("side") or 1), 1, CITY_CELL_MAX)


def _outer(cells: dict, x: int, y: int, edge: str) -> bool:
    dx, dy = _EDGE_STEP[edge]
    return (x + dx, y + dy) not in cells


def _road_gates(world: dict[str, Any], city: dict[str, Any], cells: dict) -> list[tuple[tuple[int, int], str, float]]:
    """Where the world's roads leave this city: (cell, edge, t)."""
    centre = (int(city.get("x") or 0), int(city.get("y") or 0))
    found: list[tuple[tuple[int, int], str, float]] = []
    for road in world.get("roads") or []:
        if not isinstance(road, dict):
            continue
        try:
            a = (int(road["x1"]), int(road["y1"]))
            b = (int(road["x2"]), int(road["y2"]))
        except (KeyError, TypeError, ValueError):
            continue
        if a == centre:
            start, end = a, b
        elif b == centre:
            start, end = b, a
        else:
            continue
        dx, dy = end[0] - start[0], end[1] - start[1]
        steps = max(abs(dx), abs(dy))
        if steps <= 0:
            continue
        last = None
        exit_point = None
        for i in range(steps + 1):
            px = start[0] + int(round(dx * i / steps))
            py = start[1] + int(round(dy * i / steps))
            if (px, py) in cells:
                last = (px, py)
                continue
            exit_point = (px, py)
            break
        if last is None or exit_point is None:
            continue
        ex, ey = exit_point[0] - last[0], exit_point[1] - last[1]
        axes = ["x", "y"] if abs(dx) >= abs(dy) else ["y", "x"]
        chosen = None
        for axis in axes:
            if axis == "x" and ex:
                edge = "E" if ex > 0 else "W"
            elif axis == "y" and ey:
                edge = "S" if ey > 0 else "N"
            else:
                continue
            if _outer(cells, last[0], last[1], edge):
                chosen = edge
                break
        if chosen is None:
            continue
        if chosen in ("E", "W"):
            x_edge = last[0] + (0.5 if chosen == "E" else -0.5)
            s = (x_edge - start[0]) / dx if dx else 0.0
            line = start[1] + dy * s
            t = line - (last[1] - 0.5)
        else:
            y_edge = last[1] + (0.5 if chosen == "S" else -0.5)
            s = (y_edge - start[1]) / dy if dy else 0.0
            line = start[0] + dx * s
            t = line - (last[0] - 0.5)
        found.append((last, chosen, min(0.9, max(0.1, float(t)))))
    return found


def _fallback_gate(world: dict[str, Any], city: dict[str, Any], cells: dict) -> tuple[tuple[int, int], str, float] | None:
    """A roadless city's one gate: towards the nearest other city, or a hashed outer edge."""
    centre = (int(city.get("x") or 0), int(city.get("y") or 0))
    seed = int(world.get("seed") or 1)
    best = None
    for other in world.get("cities") or []:
        if not isinstance(other, dict) or other is city or str(other.get("id") or "") == str(city.get("id") or ""):
            continue
        ox, oy = int(other.get("x") or 0), int(other.get("y") or 0)
        dist = max(abs(ox - centre[0]), abs(oy - centre[1]))
        key = (dist, str(other.get("id") or ""))
        if best is None or key < best[0]:
            best = (key, (ox - centre[0], oy - centre[1]))
    outer_edges = [
        (pos, edge) for pos in sorted(cells) for edge in ("N", "E", "S", "W") if _outer(cells, pos[0], pos[1], edge)
    ]
    if not outer_edges:
        return None
    if best is not None and best[1] != (0, 0):
        vx, vy = best[1]
        pos = max(sorted(cells), key=lambda p: ((p[0] - centre[0]) * vx + (p[1] - centre[1]) * vy))
        axes = ("x", "y") if abs(vx) >= abs(vy) else ("y", "x")
        for axis in axes:
            if axis == "x" and vx:
                edge = "E" if vx > 0 else "W"
            elif axis == "y" and vy:
                edge = "S" if vy > 0 else "N"
            else:
                continue
            if _outer(cells, pos[0], pos[1], edge):
                return pos, edge, 0.5
        for edge in ("N", "E", "S", "W"):
            if _outer(cells, pos[0], pos[1], edge):
                return pos, edge, 0.5
    pick = outer_edges[mix_hash(seed, centre[0], centre[1], _SALT_GATE) % len(outer_edges)]
    return pick[0], pick[1], 0.5


def city_ports(world: dict[str, Any], city: dict[str, Any]) -> dict[tuple[int, int], list[dict[str, Any]]]:
    """Every city cell's ports: the joins to neighbouring city cells and the gates out.

    Computed from the city record alone, so one cell can be generated without
    its neighbours. Both sides of a shared edge compute the same ``t``.
    """
    seed = int(world.get("seed") or 1)
    cache_key = (
        str(world.get("id") or ""), seed, str(city.get("id") or ""), PORT_VERSION,
        tuple(city.get("bbox") or ()), int(city.get("footprint") or 0), len(world.get("roads") or []),
        len(world.get("cities") or []),
    )
    cached = _PORTS_CACHE.get(cache_key)
    if cached is not None:
        return cached
    cells = _city_cells(city)
    ports: dict[tuple[int, int], list[dict[str, Any]]] = {pos: [] for pos in cells}
    for pos in sorted(cells):
        cell = cells[pos]
        for (dx, dy, edge_a, edge_b) in ((1, 0, "E", "W"), (0, 1, "S", "N")):
            nb = (pos[0] + dx, pos[1] + dy)
            if nb not in cells:
                continue
            ka, kb = _cell_key(*pos), _cell_key(*nb)
            ts = [(0.5, "main")]
            low = min(_side(cell), _side(cells[nb]))
            extra = (1 if low >= 48 else 0) + (1 if low >= 96 else 0)
            for k in range(extra):
                t = 0.15 + 0.7 * mix_hash(seed, ka, kb, _SALT_PORT + k) / 2**32
                ts.append((t, "street"))
            for t, cls in ts:
                ports[pos].append({"edge": edge_a, "t": t, "cls": cls, "to": [nb[0], nb[1]], "gate": None})
                ports[nb].append({"edge": edge_b, "t": t, "cls": cls, "to": [pos[0], pos[1]], "gate": None})
    gates = _road_gates(world, city, cells)
    if not gates:
        fallback = _fallback_gate(world, city, cells)
        if fallback:
            gates.append(fallback)
    if int(city.get("footprint") or len(cells)) >= 9:
        cx0, cy0 = int(city.get("x") or 0), int(city.get("y") or 0)
        column = [p for p in cells if p[0] == cx0]
        row = [p for p in cells if p[1] == cy0]
        if column:
            gates.append((min(column, key=lambda p: p[1]), "N", 0.5))
            gates.append((max(column, key=lambda p: p[1]), "S", 0.5))
        if row:
            gates.append((min(row, key=lambda p: p[0]), "W", 0.5))
            gates.append((max(row, key=lambda p: p[0]), "E", 0.5))
    seen_edges: set[tuple[tuple[int, int], str]] = set()
    used_labels: dict[str, int] = {}
    for pos, edge, t in gates:
        if (pos, edge) in seen_edges or not _outer(cells, pos[0], pos[1], edge):
            continue
        seen_edges.add((pos, edge))
        compass = _EDGE_COMPASS[edge]
        count = used_labels.get(compass, 0) + 1
        used_labels[compass] = count
        label = f"{compass.title()} Gate" if count == 1 else f"{compass.title()} Gate {count}"
        ports[pos].append({"edge": edge, "t": t, "cls": "main", "to": None, "gate": compass, "label": label})
    _PORTS_CACHE.put(cache_key, ports)
    return ports


def port_tile(port: dict[str, Any], side: int) -> tuple[int, int]:
    i = clamp_int(int(float(port.get("t") or 0.5) * side), 0, side - 1)
    edge = str(port.get("edge") or "N")
    if edge == "N":
        return i, 0
    if edge == "S":
        return i, side - 1
    if edge == "W":
        return 0, i
    return side - 1, i


# ---------------------------------------------------------------------------
# Shared edges, walls and the town field (playtest #70, #71, #72)
# ---------------------------------------------------------------------------

_OPPOSITE = {"N": "S", "S": "N", "E": "W", "W": "E"}


def edge_tiles(side: int, edge: str) -> list[int]:
    """Flat indices of one edge row of a cell, in order along the edge."""
    side = int(side)
    if edge == "N":
        return [x for x in range(side)]
    if edge == "S":
        return [(side - 1) * side + x for x in range(side)]
    if edge == "W":
        return [y * side for y in range(side)]
    return [y * side + side - 1 for y in range(side)]


def _inward(i: int, side: int, edge: str) -> int:
    dx, dy = _EDGE_STEP[edge]
    return i - dy * side - dx


def edge_arrivals(roads: bytearray, side: int, edge: str) -> list[int]:
    """Positions along an edge where a road reaches it from inside the cell."""
    out = []
    for k, i in enumerate(edge_tiles(side, edge)):
        j = _inward(i, side, edge)
        if roads[i] and 0 <= j < side * side and roads[j]:
            out.append(k)
    return out


def _avenue_edge_metres(cell: dict[str, Any], edge: str) -> list[float]:
    """Where this cell's street_mask avenues cross one of its edges, in metres along it."""
    side = _side(cell)
    mask = street_mask(int(cell.get("seed") or 1), side)
    if edge in ("N", "S"):
        row = 0 if edge == "N" else side - 1
        ks = sorted({x for x, y in mask if y == row})
    else:
        col = 0 if edge == "W" else side - 1
        ks = sorted({y for x, y in mask if x == col})
    return [(k + 0.5) * tile_metres(side) for k in ks]


def edge_joins(world: dict[str, Any], city: dict[str, Any],
               extra: dict[tuple[tuple[int, int], str], list[float]] | None = None) -> dict[tuple[tuple[int, int], str], list[float]]:
    """Where roads cross every shared edge of a city's cells: (cell, edge) -> metres along the edge.

    Playtest #70: only the ports were shared, so every other road that reached
    an edge between two cells of one town dead-ended there. A join is a port,
    or an avenue of either cell, or (``extra``) a road a stored neighbour
    already brings to the edge. Points closer than one tile of the coarser
    side are one crossing, and the earlier kind wins (ports first). Each point
    is the middle of the tile that owns it, so ``port_tile`` on either side
    lands on a tile holding that metre. Pure: the city record alone, plus
    ``extra``, decides it, so cells can be generated in any order.
    """
    seed = int(world.get("seed") or 1)
    cache_key = None
    if not extra:
        cache_key = (str(world.get("id") or ""), seed, str(city.get("id") or ""), PORT_VERSION, GEN_VERSION,
                     tuple(city.get("bbox") or ()), int(city.get("footprint") or 0), len(world.get("roads") or []),
                     len(world.get("cities") or []))
        cached = _JOINS_CACHE.get(cache_key)
        if cached is not None:
            return cached
    cells = _city_cells(city)
    ports = city_ports(world, city)
    out: dict[tuple[tuple[int, int], str], list[float]] = {}
    for pos in sorted(cells):
        for (dx, dy, edge_a, edge_b) in ((1, 0, "E", "W"), (0, 1, "S", "N")):
            nb = (pos[0] + dx, pos[1] + dy)
            if nb not in cells:
                continue
            a, b = cells[pos], cells[nb]
            merge = tile_metres(min(_side(a), _side(b)))
            points = [float(p.get("t") or 0.5) * CELL_METRES for p in ports.get(pos, [])
                      if p.get("to") and (int(p["to"][0]), int(p["to"][1])) == nb]
            points += _avenue_edge_metres(a, edge_a) + _avenue_edge_metres(b, edge_b)
            if extra:
                points += list(extra.get((pos, edge_a)) or []) + list(extra.get((nb, edge_b)) or [])
            kept: list[float] = []
            for m in points:
                if all(abs(m - k) >= merge for k in kept):
                    kept.append(m)
            kept.sort()
            out[(pos, edge_a)] = kept
            out[(nb, edge_b)] = kept
    if cache_key is not None:
        _JOINS_CACHE.put(cache_key, out)
    return out


def _join_tile(metres: float, side: int, edge: str) -> int:
    # Never a corner: a corner's inward tile lies on the other edge's row,
    # which a second shared edge would keep free of road and so cut the stub.
    k = clamp_int(int(float(metres) / tile_metres(side)), 1, max(1, side - 2))
    return edge_tiles(side, edge)[k]


def _cell_join_tiles(world: dict[str, Any], city: dict[str, Any], cell: dict[str, Any],
                     extra: dict | None = None) -> dict[str, list[int]]:
    """This cell's join tiles per shared edge (flat indices)."""
    side = _side(cell)
    pos = (int(cell.get("x") or 0), int(cell.get("y") or 0))
    joins = edge_joins(world, city, extra)
    out: dict[str, list[int]] = {}
    for edge in ("N", "E", "S", "W"):
        metres = joins.get((pos, edge))
        if metres is None:
            continue
        out[edge] = sorted({_join_tile(m, side, edge) for m in metres})
    return out


# Walls (playtest #71). A town is walled only when it really is: a hamlet or a
# village never; a town or a city of the walled eras by a hashed chance that
# grows with size; a post-collapse town behind a barricade with checkpoints.
WALL_CHANCE = {"town": 0.45, "city": 0.75, "large_city": 0.85, "metropolis": 0.9}
WALLED_ERAS = frozenset({"preindustrial", ""})
# Gates of a walled town shut overnight (minutes of the day they open and shut).
GATE_HOURS = (6 * 60, 21 * 60)


def town_walls(world: dict[str, Any], city: dict[str, Any], era: str) -> dict[str, Any]:
    """{"walled", "kind": "wall" | "barricade" | "", "manned"}. Pure, stored nowhere."""
    band = str(city.get("band") or "")
    theme = str(world.get("theme") or "")
    chance = WALL_CHANCE.get(band, 0.0)
    if chance <= 0:
        return {"walled": False, "kind": "", "manned": False}
    roll = mix_hash(int(world.get("seed") or 1), zlib.crc32(str(city.get("id") or "").encode("utf-8")), 0,
                    _SALT_WALLS) / 2**32
    if theme == "post_collapse":
        return {"walled": True, "kind": "barricade", "manned": True}
    if str(era or "") not in WALLED_ERAS or theme in _NO_RURAL_THEMES:
        return {"walled": False, "kind": "", "manned": False}
    if roll < chance:
        return {"walled": True, "kind": "wall", "manned": False}
    return {"walled": False, "kind": "", "manned": False}


def outer_edges(city: dict[str, Any], cx: int, cy: int) -> list[str]:
    cells = _city_cells(city)
    return [edge for edge in ("N", "E", "S", "W") if _outer(cells, int(cx), int(cy), edge)]


def cell_exits(world: dict[str, Any], city: dict[str, Any], cell: dict[str, Any], roads: bytearray,
               walls: dict[str, Any]) -> list[dict[str, Any]]:
    """Where the player can step out of the town from this cell (playtest #71).

    An open town: every road tile on an outer edge. A walled town: its gate
    ports, plus a gate wherever one of its avenues runs through the wall, so
    a walled town is not a one-exit trap. Works on stored rows of any version.
    """
    side = _side(cell)
    cx, cy = int(cell.get("x") or 0), int(cell.get("y") or 0)
    out: list[dict[str, Any]] = []
    seen: set[int] = set()
    ports = city_ports(world, city).get((cx, cy), [])
    walled = bool(walls.get("walled"))
    for port in ports:
        if not port.get("gate"):
            continue
        x, y = port_tile(port, side)
        i = y * side + x
        if i in seen:
            continue
        seen.add(i)
        out.append({"x": x, "y": y, "edge": str(port["edge"]), "gate": str(port.get("gate") or ""),
                    "label": str(port.get("label") or ""), "kind": "gate"})
    used: dict[str, int] = {}
    for item in out:
        used[item["gate"]] = used.get(item["gate"], 0) + 1
    for edge in outer_edges(city, cx, cy):
        for i in edge_tiles(side, edge):
            if not roads[i] or i in seen:
                continue
            if walled and roads[i] != ROAD_AVENUE:
                continue
            seen.add(i)
            item = {"x": i % side, "y": i // side, "edge": edge, "kind": "gate" if walled else "open"}
            if walled:
                compass = _EDGE_COMPASS[edge]
                used[compass] = used.get(compass, 0) + 1
                count = used[compass]
                item["gate"] = compass
                item["label"] = f"{compass.title()} Gate" if count == 1 else f"{compass.title()} Gate {count}"
            out.append(item)
    return out


def town_field(city: dict[str, Any]) -> dict[str, float]:
    """One town centre for the whole city, in town metres (playtest #72).

    The fill point is the mean of the cell centres: a one-cell town fills from
    its middle, and each extra cell pulls the point toward itself. ``r`` is
    the distance to the farthest outer corner of the footprint.
    """
    cells = list(_city_cells(city).values())
    if not cells:
        return {"x": CELL_METRES / 2, "y": CELL_METRES / 2, "r": CELL_METRES * 0.75}
    xs, ys = [], []
    corners = []
    for cell in cells:
        local = cell.get("local") or [0, 0]
        lx, ly = int(local[0]), int(local[1])
        xs.append((lx + 0.5) * CELL_METRES)
        ys.append((ly + 0.5) * CELL_METRES)
        for ox in (0, 1):
            for oy in (0, 1):
                corners.append(((lx + ox) * CELL_METRES, (ly + oy) * CELL_METRES))
    fx, fy = sum(xs) / len(xs), sum(ys) / len(ys)
    r = max(((x - fx) ** 2 + (y - fy) ** 2) ** 0.5 for x, y in corners)
    return {"x": fx, "y": fy, "r": max(1.0, r)}


def town_core(field: dict[str, float], x_m: float, y_m: float) -> float:
    """1 at the town centre falling smoothly to 0 at the farthest corner."""
    d = ((x_m - field["x"]) ** 2 + (y_m - field["y"]) ** 2) ** 0.5 / field["r"]
    t = min(1.0, max(0.0, d))
    return 1.0 - t * t * (3 - 2 * t)


def _core_fn(city: dict[str, Any], cell: dict[str, Any], side: int):
    """core(x, y) for fine tiles of one cell."""
    field = town_field(city)
    local = cell.get("local") or [0, 0]
    ox, oy = int(local[0]) * CELL_METRES, int(local[1]) * CELL_METRES
    tm = tile_metres(side)

    def core(x: float, y: float) -> float:
        return town_core(field, ox + (x + 0.5) * tm, oy + (y + 0.5) * tm)

    return core


# ---------------------------------------------------------------------------
# Grid helpers (flat arrays, index = y * side + x)
# ---------------------------------------------------------------------------


def _wards(cell: dict[str, Any], side: int, avenue: bytearray) -> tuple[list[int], list[dict[str, Any]]]:
    """District index per tile, the same flood as world_scale._flood, on flat arrays."""
    stored = [item for item in (cell.get("districts") or []) if isinstance(item, dict)]
    body_index = [index for index, item in enumerate(stored) if item.get("type") != "street"]
    street_index = next((index for index, item in enumerate(stored) if item.get("type") == "street"), -1)
    n = side * side
    own = [-1] * n
    queue: list[int] = []
    for k, index in enumerate(body_index):
        anchor = stored[index].get("anchor") or [0, 0]
        ax, ay = int(anchor[0]), int(anchor[1])
        if not (0 <= ax < side and 0 <= ay < side) or avenue[ay * side + ax]:
            continue
        own[ay * side + ax] = k
        queue.append(ay * side + ax)
    head = 0
    while head < len(queue):
        i = queue[head]
        head += 1
        x, y = i % side, i // side
        k = own[i]
        for dx, dy in _NEIGHBOURS:
            nx, ny = x + dx, y + dy
            if not (0 <= nx < side and 0 <= ny < side):
                continue
            j = ny * side + nx
            if avenue[j] or own[j] >= 0:
                continue
            own[j] = k
            queue.append(j)
    fallback = body_index[0] if body_index else -1
    ward = [fallback] * n
    for i in range(n):
        if avenue[i] and street_index >= 0:
            ward[i] = street_index
        elif own[i] >= 0:
            ward[i] = body_index[own[i]]
    return ward, stored


def _lpath(sx: int, sy: int, tx: int, ty: int, first: str, mid: int | None = None) -> list[tuple[int, int]]:
    """Tiles from (sx, sy) to (tx, ty), one bend, or two bends through ``mid`` on the first axis."""
    out = [(sx, sy)]
    x, y = sx, sy

    def go_x(target: int) -> None:
        nonlocal x
        step = 1 if target > x else -1
        while x != target:
            x += step
            out.append((x, y))

    def go_y(target: int) -> None:
        nonlocal y
        step = 1 if target > y else -1
        while y != target:
            y += step
            out.append((x, y))

    if first == "x":
        if mid is not None:
            go_x(mid)
            go_y(ty)
            go_x(tx)
        else:
            go_x(tx)
            go_y(ty)
    else:
        if mid is not None:
            go_y(mid)
            go_x(tx)
            go_y(ty)
        else:
            go_y(ty)
            go_x(tx)
    return out


def _carve(roads: bytearray, side: int, path: list[tuple[int, int]], cls: int, added: list[int]) -> bool:
    """Lay road along ``path`` until it meets an existing road. True when it joined one."""
    if not path:
        return False
    sx, sy = path[0]
    if roads[sy * side + sx]:
        return True
    for x, y in path:
        i = y * side + x
        if roads[i]:
            return True
        roads[i] = cls
        added.append(i)
    return False


def _nearest_road(roads_list: list[int], side: int, x: int, y: int, exclude: int = -1,
                  avoid: set[int] | None = None) -> tuple[int, int] | None:
    best = None
    best_d = 1 << 30
    for i in roads_list:
        if i == exclude or (avoid and i in avoid):
            continue
        d = abs(i % side - x) + abs(i // side - y)
        if d < best_d:
            best_d = d
            best = (i % side, i // side)
    return best


def _connector(rng: random.Random, roads: bytearray, side: int, road_list: list[int],
               sx: int, sy: int, first: str, avoid: set[int] | None = None) -> None:
    target = _nearest_road(road_list, side, sx, sy, avoid=avoid)
    if target is None and avoid:
        target = _nearest_road(road_list, side, sx, sy)
    if target is None:
        return
    tx, ty = target
    run = abs(tx - sx) + abs(ty - sy)
    mid = None
    if run > 48:
        if first == "x" and abs(tx - sx) > 2:
            lo, hi = sorted((sx, tx))
            mid = rng.randint(lo + 1, hi - 1)
        elif first == "y" and abs(ty - sy) > 2:
            lo, hi = sorted((sy, ty))
            mid = rng.randint(lo + 1, hi - 1)
    added: list[int] = []
    _carve(roads, side, _lpath(sx, sy, tx, ty, first, mid), ROAD_MAIN, added)
    road_list.extend(added)


def _cell_seed(world: dict[str, Any], cell: dict[str, Any], salt: int) -> int:
    return mix_hash(int(world.get("seed") or 1), int(cell.get("x") or 0), int(cell.get("y") or 0), salt)


# ---------------------------------------------------------------------------
# Stages 1 and 2: the skeleton (avenues, port and anchor connectors)
# ---------------------------------------------------------------------------


def _skeleton_roads(world: dict[str, Any], city: dict[str, Any], cell: dict[str, Any],
                    extra: dict | None = None) -> tuple[bytearray, list[dict[str, Any]], dict[str, set[int]]]:
    """Stages 1 and 2. Also returns the shared-edge shape: join tiles, and the
    other tiles of shared edge rows, which no road may use (playtest #70)."""
    side = _side(cell)
    roads = bytearray(side * side)
    for x, y in street_mask(int(cell.get("seed") or 1), side):
        roads[y * side + x] = ROAD_AVENUE
    rng = random.Random(_cell_seed(world, cell, _SALT_MAIN))
    road_list = [i for i in range(side * side) if roads[i]]
    if not road_list:
        hub = (side // 2) * side + side // 2
        roads[hub] = ROAD_MAIN
        road_list.append(hub)
    pos = (int(cell.get("x") or 0), int(cell.get("y") or 0))
    ports = sorted(
        city_ports(world, city).get(pos, []),
        key=lambda p: (str(p.get("edge")), float(p.get("t") or 0), str(p.get("cls"))),
    )
    joins = _cell_join_tiles(world, city, cell, extra)
    join_set = {i for tiles in joins.values() for i in tiles}
    shared: set[int] = set()
    for edge in joins:
        shared.update(edge_tiles(side, edge))
    # A gate port near a corner may sit on a shared edge row too; it stays.
    blocked = shared - join_set - {port_tile(p, side)[1] * side + port_tile(p, side)[0] for p in ports}
    # Connectors aim at roads off every edge row (and one row in from a shared
    # edge), so none runs along an edge: playtest #70 found a port connector
    # lying along row 0 for 33 tiles.
    band: set[int] = set()
    for edge in ("N", "E", "S", "W"):
        for i in edge_tiles(side, edge):
            band.add(i)
            if edge in joins:
                band.add(_inward(i, side, edge))
    for port in ports:
        if not port.get("gate"):
            continue  # a port to another cell of the town is one of the joins below
        px, py = port_tile(port, side)
        first = "y" if port["edge"] in ("N", "S") else "x"
        _connector(rng, roads, side, road_list, px, py, first, avoid=band)
    # Each join is a stub in from its edge tile, joined to the nearest road.
    for edge in sorted(joins):
        first = "y" if edge in ("N", "S") else "x"
        for i in joins[edge]:
            if not roads[i]:
                roads[i] = ROAD_MAIN
                road_list.append(i)
            j = _inward(i, side, edge)
            if roads[j]:
                continue
            _connector(rng, roads, side, road_list, j % side, j // side, first, avoid=band | {i})
    stored = [item for item in (cell.get("districts") or []) if isinstance(item, dict)]
    for district in stored:
        if district.get("type") == "street":
            continue
        anchor = district.get("anchor") or [0, 0]
        ax, ay = clamp_int(int(anchor[0]), 0, side - 1), clamp_int(int(anchor[1]), 0, side - 1)
        if roads[ay * side + ax]:
            continue
        target = _nearest_road(road_list, side, ax, ay)
        if target is None:
            continue
        dx, dy = target[0] - ax, target[1] - ay
        if abs(dx) >= abs(dy) and dx:
            sx, sy, first = ax + (1 if dx > 0 else -1), ay, "x"
        elif dy:
            sx, sy, first = ax, ay + (1 if dy > 0 else -1), "y"
        else:
            continue
        if not (0 <= sx < side and 0 <= sy < side):
            continue
        _connector(rng, roads, side, road_list, sx, sy, first, avoid=band)
    for i in blocked:
        roads[i] = ROAD_NONE
    return roads, ports, {"joins": join_set, "blocked": blocked}


def _extra_key(extra: dict | None) -> tuple:
    if not extra:
        return ()
    return tuple(sorted((pos, edge, tuple(round(float(m), 3) for m in metres)) for (pos, edge), metres in extra.items()))


def skeleton(world: dict[str, Any], city: dict[str, Any], cell: dict[str, Any], extra: dict | None = None) -> dict[str, Any]:
    """Stages 1 and 2 of a cell, in memory: what generation will store for those classes.

    ``extra`` is stored_edge_arrivals for this cell, the same joins get_cell
    passes to generate_cell, so a seen cell draws the roads it will get.
    """
    key = (str(world.get("id") or ""), int(world.get("seed") or 1), str(city.get("id") or ""),
           int(cell.get("x") or 0), int(cell.get("y") or 0), int(cell.get("seed") or 0), _side(cell),
           GEN_VERSION, PORT_VERSION, _extra_key(extra))
    cached = _SKELETON_CACHE.get(key)
    if cached is not None:
        return cached
    roads, ports, _shape = _skeleton_roads(world, city, cell, extra)
    side = _side(cell)
    out = {
        "side": side,
        "roads": roads,
        "segments": _segments(roads, side, None),
        "ports": ports,
    }
    _SKELETON_CACHE.put(key, out)
    return out


# ---------------------------------------------------------------------------
# Stage 3: side streets; stage 4: alleys; stage 5: connectivity
# ---------------------------------------------------------------------------


def _district_params(world: dict[str, Any], cell: dict[str, Any], stored: list[dict[str, Any]], side: int) -> list[dict[str, Any]]:
    rng = random.Random(_cell_seed(world, cell, _SALT_SIDE))
    params = []
    for district in stored:
        spec = _ward_spec(str(district.get("type") or ""))
        block_tiles = max(3, metres_to_tiles(rng.uniform(*spec["block"]), side))
        spacing = block_tiles + 1
        depth = metres_to_tiles(rng.uniform(*spec["depth"]), side)
        front = (metres_to_tiles(spec["front"][0], side), metres_to_tiles(spec["front"][1], side))
        alley = spec["alley"]
        density = normalize_density(district.get("density") or 0)
        params.append(
            {
                "type": str(district.get("type") or ""),
                "block": block_tiles,
                "spacing": spacing,
                "ox": rng.randrange(spacing),
                "oy": rng.randrange(spacing),
                "depth": depth,
                "front": front,
                "alley": alley is not None and density >= int(alley),
                "density": density,
            }
        )
    return params


def _bfs_to_road(roads: bytearray, side: int, start: int, limit: int, avoid: set[int],
                 blocked: set[int] | None = None) -> list[int] | None:
    """Shortest tile path from ``start`` to the nearest road tile not in ``avoid``, within ``limit`` steps.

    ``blocked`` tiles are never stepped on unless they are road already.
    """
    parent = {start: -1}
    frontier = deque([(start, 0)])
    while frontier:
        i, d = frontier.popleft()
        if i != start and roads[i] and i not in avoid:
            path = []
            while i != -1:
                path.append(i)
                i = parent[i]
            path.reverse()
            return path
        if d >= limit:
            continue
        x, y = i % side, i // side
        for dx, dy in _NEIGHBOURS:
            nx, ny = x + dx, y + dy
            if 0 <= nx < side and 0 <= ny < side:
                j = ny * side + nx
                if j not in parent and not (blocked and j in blocked and not roads[j]):
                    parent[j] = i
                    frontier.append((j, d + 1))
    return None


def _side_streets(roads: bytearray, side: int, ward: list[int], params: list[dict[str, Any]],
                  reserved: bytearray, blocked: set[int] | None = None) -> None:
    if side < 16:
        return
    sources = [i for i in range(side * side) if roads[i]]
    # Each pass shoots cross streets off the lines the last pass laid, so the
    # grid fills in from the main roads outwards.
    for _pass in range(SIDE_STREET_PASSES):
        new_tiles: list[int] = []
        for i in sources:
            if roads[i] == ROAD_NONE:
                continue
            x, y = i % side, i // side
            horiz = (x > 0 and roads[i - 1]) or (x < side - 1 and roads[i + 1])
            vert = (y > 0 and roads[i - side]) or (y < side - 1 and roads[i + side])
            if horiz and not vert:
                shots = ((0, -1), (0, 1))
            elif vert and not horiz:
                shots = ((-1, 0), (1, 0))
            else:
                continue
            for dx, dy in shots:
                fx, fy = x + dx, y + dy
                if not (0 <= fx < side and 0 <= fy < side):
                    continue
                first = fy * side + fx
                if roads[first] or reserved[first]:
                    continue
                d = ward[first]
                if d < 0 or d >= len(params):
                    continue
                prm = params[d]
                if prm["type"] == "street":
                    continue
                along = x if dx == 0 else y
                offset = prm["ox"] if dx == 0 else prm["oy"]
                if (along - offset) % prm["spacing"]:
                    continue
                gap = max(1, prm["block"] // 2)
                crowded = False
                for k in range(1, gap + 1):
                    for sgn in (-1, 1):
                        qx = fx + (sgn * k if dx == 0 else 0)
                        qy = fy + (sgn * k if dy == 0 else 0)
                        if 0 <= qx < side and 0 <= qy < side and roads[qy * side + qx]:
                            crowded = True
                            break
                    if crowded:
                        break
                if crowded:
                    continue
                # The line runs on across a ward boundary until it meets a
                # road: stopping one tile past the boundary left most lines
                # dangling in wards whose own streets had not been laid yet.
                line: list[int] = []
                cx, cy = fx, fy
                joined = False
                while 0 <= cx < side and 0 <= cy < side:
                    j = cy * side + cx
                    if roads[j]:
                        joined = True
                        break
                    if reserved[j]:
                        break
                    line.append(j)
                    side_hit = False
                    if len(line) >= 2:
                        for sx, sy in ((dy, dx), (-dy, -dx)):
                            qx, qy = cx + sx, cy + sy
                            if 0 <= qx < side and 0 <= qy < side and roads[qy * side + qx]:
                                side_hit = True
                                break
                    if side_hit:
                        joined = True
                        break
                    cx += dx
                    cy += dy
                if not line:
                    continue
                if not joined:
                    if len(line) < 2:
                        continue
                    for j in line:
                        roads[j] = ROAD_STREET
                    ext = _bfs_to_road(roads, side, line[-1], min(len(line) - 1, 2 * prm["spacing"]), set(line),
                                       blocked)
                    if ext is None:
                        for j in line:
                            roads[j] = ROAD_NONE
                        continue
                    for j in ext:
                        if not roads[j]:
                            roads[j] = ROAD_STREET
                            line.append(j)
                    new_tiles.extend(line)
                    continue
                for j in line:
                    roads[j] = ROAD_STREET
                new_tiles.extend(line)
        sources = new_tiles


def _components(side: int, inside: bytearray) -> tuple[list[int], list[list[int]]]:
    """4-connected components of tiles where ``inside`` is set, in row-major order of first tile."""
    comp = [-1] * (side * side)
    groups: list[list[int]] = []
    for start in range(side * side):
        if not inside[start] or comp[start] >= 0:
            continue
        gid = len(groups)
        comp[start] = gid
        group = [start]
        head = 0
        while head < len(group):
            i = group[head]
            head += 1
            x, y = i % side, i // side
            for dx, dy in _NEIGHBOURS:
                nx, ny = x + dx, y + dy
                if 0 <= nx < side and 0 <= ny < side:
                    j = ny * side + nx
                    if inside[j] and comp[j] < 0:
                        comp[j] = gid
                        group.append(j)
        group.sort()
        groups.append(group)
    return comp, groups


def _alleys(roads: bytearray, side: int, ward: list[int], params: list[dict[str, Any]], reserved: bytearray) -> None:
    free = bytearray(1 if not roads[i] else 0 for i in range(side * side))
    comp, groups = _components(side, free)
    for gid, group in enumerate(groups):
        d = ward[group[0]]
        if d < 0 or d >= len(params) or not params[d]["alley"]:
            continue
        xs = [i % side for i in group]
        ys = [i // side for i in group]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        w, h = x1 - x0 + 1, y1 - y0 + 1
        if min(w, h) <= 2 * params[d]["depth"] + 1:
            continue
        if w >= h:
            row = y0 + h // 2
            run = [row * side + x for x in range(x0, x1 + 1)]
        else:
            col = x0 + w // 2
            run = [y * side + col for y in range(y0, y1 + 1)]
        best: list[int] = []
        current: list[int] = []
        for i in run:
            if comp[i] == gid and not reserved[i]:
                current.append(i)
                if len(current) > len(best):
                    best = list(current)
            else:
                current = []
        if len(best) < 3:
            continue
        for i in best:
            roads[i] = ROAD_ALLEY


def _port_tiles(ports: list[dict[str, Any]], side: int) -> list[int]:
    return sorted({port_tile(p, side)[1] * side + port_tile(p, side)[0] for p in ports})


def _connect_all(roads: bytearray, side: int, ports: list[dict[str, Any]], blocked: set[int] | None = None,
                 joins: Iterable[int] = ()) -> None:
    """Stage 5: every road tile reachable from the ports; join any island to the network.

    ``blocked`` tiles (shared edge rows off the joins) never carry a joining
    street; ``joins`` must end up on the network like the ports. With joins
    the flood starts from one of them only, so two ports or joins on separate
    pieces of road get joined instead of both counting as reached.
    """
    joins = sorted(set(int(i) for i in joins))
    starts = [i for i in sorted(set(_port_tiles(ports, side)) | set(joins)) if roads[i]]
    if joins:
        starts = starts[:1]
    if not starts:
        starts = [next((i for i in range(side * side) if roads[i]), 0)]
    reached = bytearray(side * side)

    def flood(seeds: Iterable[int]) -> None:
        queue = deque()
        for s in seeds:
            if roads[s] and not reached[s]:
                reached[s] = 1
                queue.append(s)
        while queue:
            i = queue.popleft()
            x, y = i % side, i // side
            for dx, dy in _NEIGHBOURS:
                nx, ny = x + dx, y + dy
                if 0 <= nx < side and 0 <= ny < side:
                    j = ny * side + nx
                    if roads[j] and not reached[j]:
                        reached[j] = 1
                        queue.append(j)

    flood(starts)
    for _guard in range(side * side):
        island = next((i for i in range(side * side) if roads[i] and not reached[i]), -1)
        if island < 0:
            break
        # Multi-source search from the island's tiles to any reached road tile.
        members = deque([island])
        seen_island = {island}
        while members:
            i = members.popleft()
            x, y = i % side, i // side
            for dx, dy in _NEIGHBOURS:
                nx, ny = x + dx, y + dy
                if 0 <= nx < side and 0 <= ny < side:
                    j = ny * side + nx
                    if roads[j] and not reached[j] and j not in seen_island:
                        seen_island.add(j)
                        members.append(j)
        parent = {i: -1 for i in seen_island}
        frontier = deque(sorted(seen_island))
        hit = -1
        while frontier:
            i = frontier.popleft()
            if reached[i]:
                hit = i
                break
            x, y = i % side, i // side
            for dx, dy in _NEIGHBOURS:
                nx, ny = x + dx, y + dy
                if 0 <= nx < side and 0 <= ny < side:
                    j = ny * side + nx
                    if j not in parent and not (blocked and j in blocked and not roads[j]):
                        parent[j] = i
                        frontier.append(j)
        if hit < 0:
            break
        i = parent[hit]
        while i != -1 and i not in seen_island:
            if not roads[i]:
                roads[i] = ROAD_STREET
            i = parent[i]
        # The island is joined now; flood from it (hit is already reached).
        flood([island])
    for i in range(side * side):
        if roads[i] and not reached[i]:
            raise RuntimeError("town grid: a road tile is not connected to the network")
    for i in sorted(set(_port_tiles(ports, side)) | set(joins)):
        if not roads[i]:
            raise RuntimeError("town grid: a port is not on a road")


# ---------------------------------------------------------------------------
# Segments
# ---------------------------------------------------------------------------


def _segments(roads: bytearray, side: int, ward: list[int] | None) -> list[dict[str, Any]]:
    """Maximal straight runs of one road class (main runs also split by ward)."""
    segs: list[dict[str, Any]] = []

    def key(i: int) -> tuple[int, int]:
        cls = roads[i]
        return (cls, ward[i] if (ward is not None and cls == ROAD_MAIN) else -1)

    for y in range(side):
        x = 0
        while x < side:
            i = y * side + x
            if not roads[i]:
                x += 1
                continue
            k = key(i)
            x1 = x
            while x1 + 1 < side and roads[y * side + x1 + 1] and key(y * side + x1 + 1) == k:
                x1 += 1
            if x1 > x:
                segs.append({"id": len(segs), "cls": k[0], "x0": x, "y0": y, "x1": x1, "y1": y})
            x = x1 + 1
    for x in range(side):
        y = 0
        while y < side:
            i = y * side + x
            if not roads[i]:
                y += 1
                continue
            k = key(i)
            y1 = y
            while y1 + 1 < side and roads[(y1 + 1) * side + x] and key((y1 + 1) * side + x) == k:
                y1 += 1
            if y1 > y:
                segs.append({"id": len(segs), "cls": k[0], "x0": x, "y0": y, "x1": x, "y1": y1})
            y = y1 + 1
    # A road tile in no run of two (a lone stub) is its own segment.
    covered = bytearray(side * side)
    for seg in segs:
        for yy in range(seg["y0"], seg["y1"] + 1):
            for xx in range(seg["x0"], seg["x1"] + 1):
                covered[yy * side + xx] = 1
    for i in range(side * side):
        if roads[i] and not covered[i]:
            segs.append({"id": len(segs), "cls": roads[i], "x0": i % side, "y0": i // side, "x1": i % side, "y1": i // side})
    return segs


def _segment_index(segs: list[dict[str, Any]], side: int) -> tuple[list[int], list[int]]:
    hseg = [-1] * (side * side)
    vseg = [-1] * (side * side)
    for seg in segs:
        if seg["y0"] == seg["y1"] and seg["x1"] > seg["x0"]:
            for xx in range(seg["x0"], seg["x1"] + 1):
                hseg[seg["y0"] * side + xx] = seg["id"]
        elif seg["x0"] == seg["x1"] and seg["y1"] > seg["y0"]:
            for yy in range(seg["y0"], seg["y1"] + 1):
                vseg[yy * side + seg["x0"]] = seg["id"]
        else:
            i = seg["y0"] * side + seg["x0"]
            if hseg[i] < 0:
                hseg[i] = seg["id"]
            if vseg[i] < 0:
                vseg[i] = seg["id"]
    return hseg, vseg


# ---------------------------------------------------------------------------
# Plots (TownGrid.md 3.3)
# ---------------------------------------------------------------------------


def _grow_rect(side: int, x: int, y: int, max_w: int, max_h: int, ok) -> tuple[int, int, int, int]:
    """Largest rectangle grown from (x, y) by whole rows and columns, each tile passing ``ok``."""
    x0, y0, x1, y1 = x, y, x, y
    grew = True
    while grew:
        grew = False
        for direction in ("E", "S", "W", "N"):
            if direction in ("E", "W") and x1 - x0 + 1 >= max_w:
                continue
            if direction in ("N", "S") and y1 - y0 + 1 >= max_h:
                continue
            if direction == "E":
                nx = x1 + 1
                if nx < side and all(ok(nx, yy) for yy in range(y0, y1 + 1)):
                    x1 = nx
                    grew = True
            elif direction == "W":
                nx = x0 - 1
                if nx >= 0 and all(ok(nx, yy) for yy in range(y0, y1 + 1)):
                    x0 = nx
                    grew = True
            elif direction == "S":
                ny = y1 + 1
                if ny < side and all(ok(xx, ny) for xx in range(x0, x1 + 1)):
                    y1 = ny
                    grew = True
            else:
                ny = y0 - 1
                if ny >= 0 and all(ok(xx, ny) for xx in range(x0, x1 + 1)):
                    y0 = ny
                    grew = True
    return x0, y0, x1 - x0 + 1, y1 - y0 + 1


def _rect_frontage(roads: bytearray, side: int, rect: tuple[int, int, int, int]) -> tuple[int, int, str] | None:
    """The road tile orthogonally beside a rectangle nearest its middle, and which side it is on."""
    x0, y0, w, h = rect
    mx, my = x0 + (w - 1) / 2, y0 + (h - 1) / 2
    best = None
    for edge in ("S", "N", "E", "W"):
        if edge in ("N", "S"):
            ry = y0 - 1 if edge == "N" else y0 + h
            if not (0 <= ry < side):
                continue
            for xx in range(x0, x0 + w):
                if roads[ry * side + xx]:
                    d = abs(xx - mx) + abs(ry - my)
                    if best is None or d < best[0]:
                        best = (d, xx, ry, edge)
        else:
            rx = x0 - 1 if edge == "W" else x0 + w
            if not (0 <= rx < side):
                continue
            for yy in range(y0, y0 + h):
                if roads[yy * side + rx]:
                    d = abs(rx - mx) + abs(yy - my)
                    if best is None or d < best[0]:
                        best = (d, rx, yy, edge)
    if best is None:
        return None
    return best[1], best[2], best[3]


def _cut_plots(rng: random.Random, roads: bytearray, side: int, ward: list[int], params: list[dict[str, Any]],
               stored: list[dict[str, Any]], gates: list[dict[str, Any]], hseg: list[int], vseg: list[int],
               core=None) -> list[dict[str, Any]]:
    """``core(x, y)`` (town_field) lets frontage plots run deeper toward the
    town centre, so built-up blocks have no bare middles (playtest #72)."""
    n_tiles = side * side
    taken = bytearray(n_tiles)
    plots: list[dict[str, Any]] = []

    def seg_for(fx: int, fy: int, edge: str) -> int | None:
        i = fy * side + fx
        primary = hseg[i] if edge in ("N", "S") else vseg[i]
        other = vseg[i] if edge in ("N", "S") else hseg[i]
        found = primary if primary >= 0 else other
        return found if found >= 0 else None

    def add(rect, kind, d, front, flags=None, extra=None) -> dict[str, Any]:
        x0, y0, w, h = rect
        for yy in range(y0, y0 + h):
            for xx in range(x0, x0 + w):
                taken[yy * side + xx] = 1
        plot: dict[str, Any] = {"n": len(plots), "r": [x0, y0, w, h], "d": d, "k": kind}
        if front is not None:
            plot["f"] = [front[0], front[1]]
            seg = seg_for(front[0], front[1], front[2])
            if seg is not None:
                plot["seg"] = seg
        if flags:
            plot["fl"] = list(flags)
        if extra:
            plot.update(extra)
        plots.append(plot)
        return plot

    # Gates first: a small square inside the edge beside each gate port. When
    # no 2x2 fits, a single tile does: a gate with no plot was never drawn
    # (playtest #71, Harmere's South Gate).
    g = 2 if side >= 48 else 1
    for port in gates:
        px, py = port_tile(port, side)
        edge = port["edge"]
        cands = []
        for gg in ((g, 1) if g > 1 else (g,)):
            if edge in ("N", "S"):
                ys = list(range(0, gg)) if edge == "N" else list(range(side - gg, side))
                options = [list(range(px + 1, px + 1 + gg)), list(range(px - gg, px))]
                cands += [(xs, ys) for xs in options]
            else:
                xs = list(range(0, gg)) if edge == "W" else list(range(side - gg, side))
                options = [list(range(py + 1, py + 1 + gg)), list(range(py - gg, py))]
                cands += [(xs, ys) for ys in options]
        for xs, ys in cands:
            if not all(0 <= xx < side for xx in xs) or not all(0 <= yy < side for yy in ys):
                continue
            if any(roads[yy * side + xx] or taken[yy * side + xx] for yy in ys for xx in xs):
                continue
            rect = (min(xs), min(ys), len(xs), len(ys))
            front = _rect_frontage(roads, side, rect)
            if front is None:
                continue
            add(rect, "gate", ward[min(ys) * side + min(xs)], front,
                extra={"name": str(port.get("label") or f"{_EDGE_COMPASS[edge].title()} Gate"),
                       "gate": port.get("gate")})
            break

    # Landmarks: the temple, the hall and the barracks stand at their ward's anchor.
    lm_tiles = metres_to_tiles(LANDMARK_METRES, side)
    landmark_for = {"temple": "temple", "government": "office", "military": "barracks"}
    for index, district in enumerate(stored):
        kind = landmark_for.get(str(district.get("type") or ""))
        if not kind:
            continue
        anchor = district.get("anchor") or [0, 0]
        ax, ay = clamp_int(int(anchor[0]), 0, side - 1), clamp_int(int(anchor[1]), 0, side - 1)
        start = None
        for radius in range(0, 3):
            for yy in range(ay - radius, ay + radius + 1):
                for xx in range(ax - radius, ax + radius + 1):
                    if 0 <= xx < side and 0 <= yy < side:
                        i = yy * side + xx
                        if not roads[i] and not taken[i] and ward[i] == index:
                            start = (xx, yy)
                            break
                if start:
                    break
            if start:
                break
        if start is None:
            continue

        def ok(xx: int, yy: int, _index=index) -> bool:
            i = yy * side + xx
            return not roads[i] and not taken[i] and ward[i] == _index

        rect = _grow_rect(side, start[0], start[1], lm_tiles, lm_tiles, ok)
        front = _rect_frontage(roads, side, rect)
        if front is None:
            continue
        extra: dict[str, Any] = {}
        if kind == "temple":
            extra["vk"] = "temple"
        else:
            extra["name"] = str(district.get("name") or "")
        add(rect, kind, index, front, flags=["anchor"], extra=extra)

    # Frontage cuts, then leftovers as yards.
    free = bytearray(1 if not roads[i] else 0 for i in range(n_tiles))
    _comp, blocks = _components(side, free)
    step_in = {"N": (0, 1), "S": (0, -1), "E": (-1, 0), "W": (1, 0)}
    for block in blocks:
        block_set = set(block)
        for t in block:
            if taken[t]:
                continue
            x, y = t % side, t // side
            road_edge = None
            for edge in ("N", "E", "S", "W"):
                ex, ey = _EDGE_STEP[edge]
                nx, ny = x + ex, y + ey
                if 0 <= nx < side and 0 <= ny < side and roads[ny * side + nx]:
                    road_edge = edge
                    break
            if road_edge is None:
                continue
            d = ward[t]
            prm = params[d] if 0 <= d < len(params) else None
            if prm is None:
                continue
            ix, iy = step_in[road_edge]
            deep = prm["depth"]
            c = core(x, y) if core is not None else 0.0
            run = 0
            cx, cy = x, y
            reach = side if c > 0 else 2 * deep + 2
            while 0 <= cx < side and 0 <= cy < side and (cy * side + cx) in block_set and not taken[cy * side + cx] and run < reach:
                run += 1
                cx += ix
                cy += iy
            if c > 0:
                # Toward the town centre a plot runs back to the middle of its
                # block, so the block is built through (playtest #72).
                deep = max(deep, int(round(deep + max(0, (run + 1) // 2 - deep) * c)))
                run = min(run, 2 * deep + 2)
            if run <= deep + 1:
                depth = run
            elif run < 2 * deep:
                depth = (run + 1) // 2
            else:
                depth = deep
            depth = max(1, depth)
            width = rng.randint(prm["front"][0], max(prm["front"][0], prm["front"][1]))
            ax_dx, ax_dy = (1, 0) if road_edge in ("N", "S") else (0, 1)
            ex, ey = _EDGE_STEP[road_edge]

            def column_ok(col_x: int, col_y: int, need: int) -> int:
                got = 0
                qx, qy = col_x, col_y
                while got < need:
                    if not (0 <= qx < side and 0 <= qy < side):
                        break
                    q = qy * side + qx
                    if q not in block_set or taken[q]:
                        break
                    got += 1
                    qx += ix
                    qy += iy
                return got

            depth = max(1, min(depth, column_ok(x, y, depth)))
            cols = 1
            while cols < width:
                nx, ny = x + ax_dx * cols, y + ax_dy * cols
                if not (0 <= nx < side and 0 <= ny < side):
                    break
                ni = ny * side + nx
                if ni not in block_set or taken[ni]:
                    break
                rx, ry = nx + ex, ny + ey
                if not (0 <= rx < side and 0 <= ry < side) or not roads[ry * side + rx]:
                    break
                if column_ok(nx, ny, depth) < depth:
                    break
                cols += 1
            if road_edge in ("N", "S"):
                rx0 = x
                ry0 = y if road_edge == "N" else y - depth + 1
                rect = (rx0, ry0, cols, depth)
            else:
                ry0 = y
                rx0 = x if road_edge == "W" else x - depth + 1
                rect = (rx0, ry0, depth, cols)
            mid = cols // 2
            fx = x + ax_dx * mid + ex
            fy = y + ax_dy * mid + ey
            front = (fx, fy, road_edge)
            flags = []
            rx0, ry0, rw, rh = rect
            perpendicular = ("E", "W") if road_edge in ("N", "S") else ("N", "S")
            corner = False
            for edge in perpendicular:
                if edge in ("E", "W"):
                    qx = rx0 - 1 if edge == "W" else rx0 + rw
                    if 0 <= qx < side and any(roads[yy * side + qx] for yy in range(ry0, ry0 + rh)):
                        corner = True
                else:
                    qy = ry0 - 1 if edge == "N" else ry0 + rh
                    if 0 <= qy < side and any(roads[qy * side + xx] for xx in range(rx0, rx0 + rw)):
                        corner = True
            if corner:
                flags.append("corner")
            add(rect, None, d, front, flags=flags)
        cap = 8
        for t in block:
            if taken[t]:
                continue
            x, y = t % side, t // side

            def ok_left(xx: int, yy: int) -> bool:
                i = yy * side + xx
                return i in block_set and not taken[i]

            x1 = x
            while x1 + 1 < side and x1 - x + 1 < cap and ok_left(x1 + 1, y):
                x1 += 1
            y1 = y
            while y1 + 1 < side and y1 - y + 1 < cap and all(ok_left(xx, y1 + 1) for xx in range(x, x1 + 1)):
                y1 += 1
            w, h = x1 - x + 1, y1 - y + 1
            if w * h < 2:
                taken[t] = 1  # plain ground, not a plot
                continue
            add((x, y, w, h), "yard", ward[t], None)
    return plots


# ---------------------------------------------------------------------------
# Notices, stalls and rolls (TownGrid.md 3.3, 3.4)
# ---------------------------------------------------------------------------


def notices_for_cell(city: dict[str, Any], cx: int, cy: int) -> list[dict[str, Any]]:
    """Notices whose destination is this cell, from every cell's list, by id."""
    found: dict[str, dict[str, Any]] = {}
    for cell in city.get("cells") or []:
        if not isinstance(cell, dict):
            continue
        for notice in cell.get("notices") or []:
            if not isinstance(notice, dict):
                continue
            if int(notice.get("x") or 0) == int(cx) and int(notice.get("y") or 0) == int(cy):
                nid = str(notice.get("id") or "")
                if nid and nid not in found:
                    found[nid] = notice
    return [found[key] for key in sorted(found)]


def _nearest_road_tile(roads: bytearray, side: int, x: int, y: int) -> tuple[int, int] | None:
    x, y = clamp_int(x, 0, side - 1), clamp_int(y, 0, side - 1)
    path = _bfs_to_road(roads, side, y * side + x, side * 2, set()) if not roads[y * side + x] else [y * side + x]
    if not path:
        return None
    i = path[-1]
    return i % side, i // side


def _fitted_kinds(kinds: Iterable[str], era: str, size: str) -> tuple[list[str], list[str]]:
    from app.venues import kind_allowed, kind_for_era

    fitted: list[str] = []
    for kind in kinds:
        k = kind_for_era(kind, era) if era else kind
        if k and k not in fitted:
            fitted.append(k)
    plausible = [k for k in fitted if kind_allowed(k, size)]
    return fitted, plausible


# Frontage plots per unit of a kind's village cap (see kind_cap).
CAP_PLOTS_PER_UNIT = 32


def kind_cap(kind: str, frontage_plots: int, density: int) -> int:
    """How many plots of one kind a district may hold.

    Build deviation from TownGrid.md 3.4 (slice A probe): the design scaled
    the village cap by ``side / 64``. Measured on a 25-cell city that capped
    market wards at about 0.19 shops per frontage plot, below craft wards
    (0.21), because a market ward has several hundred frontage plots and the
    per-kind caps ran out long before the rolls did. Scaling by the
    district's own frontage plots keeps the cap proportional to the ward,
    so the share follows the roll rates and a market ward is mostly shops.
    """
    from app.venues import VENUE_KINDS

    base = int((VENUE_KINDS.get(kind) or {}).get("max") or 1)
    scaled = base * max(0, int(frontage_plots)) / CAP_PLOTS_PER_UNIT * max(int(density), 20) / 50
    return max(base, int(round(scaled)))


def _roll_otherwise(rng: random.Random, ward_type: str) -> str:
    rows = OTHERWISE.get(ward_type) or OTHERWISE["residential"]
    total = sum(weight for _kind, weight in rows)
    pick = rng.random() * total
    for kind, weight in rows:
        pick -= weight
        if pick < 0:
            return kind
    return rows[-1][0]


def _roll_rural(rng: random.Random) -> str:
    total = sum(weight for _kind, weight in RURAL_KINDS)
    pick = rng.random() * total
    for kind, weight in RURAL_KINDS:
        pick -= weight
        if pick < 0:
            return kind
    return RURAL_KINDS[-1][0]


def _assign_kinds(world: dict[str, Any], city: dict[str, Any], cell: dict[str, Any], stored: list[dict[str, Any]],
                  plots: list[dict[str, Any]], roads: bytearray, side: int, era: str, core=None) -> dict[str, Any]:
    """Kinds for every plot. ``core(x, y)`` (town_field) puts the shops and
    the built lots toward the town centre and the farmland at its fringe
    (playtest #72); without it every ward rolls alike, as in v1."""
    from app.local_intel import stalls_for_district
    from app.world_scale import theme_allows_slavery

    size = settlement_size_for_band(str(city.get("band") or ""))
    theme = str(world.get("theme") or "")
    slavery = bool(world.get("allows_slavery")) or theme_allows_slavery(theme)
    counts: dict[tuple[int, str], int] = {}
    caps: dict[tuple[int, str], int] = {}
    report = {"stalls": 0, "stalls_placed": 0, "stalls_unplaced": 0, "notices": 0}

    def cap_left(d: int, kind: str) -> bool:
        cap = caps.get((d, kind))
        if cap is None:
            density = normalize_density((stored[d] if 0 <= d < len(stored) else {}).get("density") or 0)
            cap = caps[(d, kind)] = kind_cap(kind, ward_frontage.get(d, 0), density)
        return counts.get((d, kind), 0) < cap

    def take(plot: dict[str, Any], kind: str) -> None:
        plot["vk"] = kind
        plot["k"] = "service" if kind in SERVICE_KINDS else "shop"
        counts[(int(plot["d"]), kind)] = counts.get((int(plot["d"]), kind), 0) + 1

    frontage = [p for p in plots if p.get("f") is not None and p.get("k") not in _NOT_STALL_TARGETS]
    ward_frontage: dict[int, int] = {}
    for p in frontage:
        ward_frontage[int(p["d"])] = ward_frontage.get(int(p["d"]), 0) + 1

    # Notices: placed on the road tile nearest their spot, recorded on the nearest frontage plot.
    for notice in notices_for_cell(city, int(cell.get("x") or 0), int(cell.get("y") or 0)):
        tile = _nearest_road_tile(roads, side, int(notice.get("fine_x") or 0), int(notice.get("fine_y") or 0))
        if tile is None:
            continue
        is_guild = str(notice.get("kind") or "") == "guild"
        pool = frontage if is_guild else [p for p in plots if p.get("f") is not None]
        if is_guild:
            pool = [p for p in pool if p.get("k") is None]
        if not pool:
            continue
        target = min(pool, key=lambda p: (abs(p["f"][0] - tile[0]) + abs(p["f"][1] - tile[1]), p["n"]))
        flags = target.setdefault("fl", [])
        if "notice" not in flags:
            flags.append("notice")
        target.setdefault("nt", []).append(str(notice.get("id") or ""))
        if is_guild:
            if "guild" not in flags:
                flags.append("guild")
            take(target, "guild_hall")
        report["notices"] += 1

    # Stalls already told to players: forced shops inside their own district.
    for index, district in enumerate(stored):
        if district.get("type") == "street" or int(district.get("shop_count") or 0) <= 0:
            continue
        stalls = stalls_for_district(cell, district, theme=theme, slavery=slavery)
        shady = str(district.get("type") or "") == "black_market" or "black_market" in set(district.get("permissions") or [])
        for stall_no, stall in enumerate(stalls):
            if stall.get("filler"):
                continue
            report["stalls"] += 1
            sx, sy = int(stall["fine_x"]), int(stall["fine_y"])
            pool = [p for p in frontage if p["d"] == index and "stall" not in (p.get("fl") or []) and "guild" not in (p.get("fl") or [])]
            if not pool:
                report["stalls_unplaced"] += 1
                continue

            def dist(p: dict[str, Any]) -> tuple[float, int]:
                r = p["r"]
                mx, my = r[0] + (r[2] - 1) / 2, r[1] + (r[3] - 1) / 2
                return ((mx - sx) ** 2 + (my - sy) ** 2, p["n"])

            target = min(pool, key=dist)
            good = str(stall.get("good") or "general")
            fence = shady or good in _FENCE_GOODS
            row = _FENCE_KINDS if good in _FENCE_GOODS or good not in STALL_GOOD_KINDS else STALL_GOOD_KINDS[good]
            fitted, plausible = _fitted_kinds(row, era, size)
            if not fitted:
                fitted, plausible = _fitted_kinds(("general_store",), era, size)
            choices = plausible or fitted
            open_kinds = [k for k in choices if cap_left(index, k)]
            if open_kinds:
                h = mix_hash(_cell_seed(world, cell, _SALT_ROLLS), index, stall_no, 3)
                kind = open_kinds[h % len(open_kinds)]
            else:
                kind = min(choices, key=lambda k: (counts.get((index, k), 0), choices.index(k)))
            if target.get("k") is None:
                take(target, kind)
            flags = target.setdefault("fl", [])
            flags.append("stall")
            if fence:
                flags.append("fence")
            target["st"] = f"{district.get('id') or index}:{stall_no}"
            report["stalls_placed"] += 1

    # Every other frontage plot rolls by its ward.
    from app.venues import plausible_kinds

    possible = set(plausible_kinds(size, era))
    rng = random.Random(_cell_seed(world, cell, _SALT_ROLLS))
    rural_rng = random.Random(_cell_seed(world, cell, _SALT_RURAL))
    rural_ok = theme not in _NO_RURAL_THEMES and str(era or "") != "future"
    empty_scale = 2.0 if theme == "post_collapse" else 1.0

    def plot_core(plot: dict[str, Any]) -> float | None:
        if core is None:
            return None
        r = plot["r"]
        return core(r[0] + (r[2] - 1) / 2, r[1] + (r[3] - 1) / 2)

    for plot in plots:
        if plot.get("k") is not None:
            # A leftover yard on the fringe is farmland, not a bare lot.
            if plot.get("k") == "yard" and plot.get("f") is None and rural_ok:
                c = plot_core(plot)
                if c is not None and c < FRINGE_CORE:
                    plot["k"] = _roll_rural(rural_rng)
            continue
        d = int(plot["d"])
        district = stored[d] if 0 <= d < len(stored) else {}
        ward_type = str(district.get("type") or "residential")
        density = normalize_density(district.get("density") or 0)
        base = SHOP_BASE.get(ward_type, SHOP_BASE["residential"])
        p_shop = base * (0.5 + density / 100)
        if ward_type == "residential" and "corner" in (plot.get("fl") or []):
            p_shop *= 3
        p_empty = max(0.0, 0.25 - density / 400) * empty_scale
        c = plot_core(plot)
        fringe = False
        if c is not None:
            # Shops gather toward the town centre; the built-up middle has
            # almost no empty lots (playtest #72).
            p_shop *= 0.4 + 1.2 * c
            p_empty *= (1 - c) ** 2
            fringe = rural_ok and c < FRINGE_CORE
        if rng.random() < p_shop:
            table = [(k, w.get(ward_type, 0)) for k, w in KIND_WEIGHTS.items() if k in possible and w.get(ward_type, 0) > 0]
            table = [(k, w) for k, w in table if cap_left(d, k)]
            if table:
                total = sum(w for _k, w in table)
                pick = rng.random() * total
                chosen = table[-1][0]
                for k, w in table:
                    pick -= w
                    if pick < 0:
                        chosen = k
                        break
                take(plot, chosen)
                continue
            rng.random()  # keep the stream's shape when every kind is capped
            plot["k"] = _roll_otherwise(rng, ward_type)
            continue
        if rng.random() < p_empty:
            plot["k"] = _roll_rural(rural_rng) if fringe else "empty"
            continue
        kind = _roll_otherwise(rng, ward_type)
        if fringe and kind in ("house", "yard", "warehouse") and rural_rng.random() < 0.75 * (1 - c / FRINGE_CORE):
            kind = _roll_rural(rural_rng)
        plot["k"] = kind
    return report


# ---------------------------------------------------------------------------
# Names
# ---------------------------------------------------------------------------


def _norm_name(text: str) -> str:
    return " ".join(str(text or "").lower().split())


class NameOwners:
    """Which cell of a city may use a name: each name belongs to exactly one cell.

    Names must be unique in a city, and a cell must come out the same whichever
    cell was generated first (TownGrid.md 10, determinism). Excluding the names
    already stored in other cells broke the second rule whenever two cells drew
    the same name, which with a few hundred street names per city was most
    of the time. Instead every name hashes to one owning cell, weighted by how
    many names a cell needs (streets by side, buildings by side squared), and a
    cell draws until it renders a name it owns. Two cells can never hold the
    same name, and no cell needs to know what the others drew.
    """

    def __init__(self, world: dict[str, Any], city: dict[str, Any]) -> None:
        cells = sorted(_city_cells(city).items())
        self.keys = [pos for pos, _cell in cells]
        self.seed = int(world.get("seed") or 1)
        self.salt = zlib.crc32(str(city.get("id") or "").encode("utf-8"))
        self.cum: dict[str, list[int]] = {}
        for kind, power in (("street_name", 1), ("venue_name", 2)):
            total = 0
            cum = []
            for _pos, cell in cells:
                total += _side(cell) ** power
                cum.append(total)
            self.cum[kind] = cum

    def owner(self, kind: str, name: str) -> tuple[int, int]:
        cum = self.cum[kind]
        if len(cum) == 1:
            return self.keys[0]
        h = mix_hash(self.seed, zlib.crc32(_norm_name(name).encode("utf-8")), self.salt, _SALT_NAMES)
        point = h % cum[-1]
        lo, hi = 0, len(cum) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if cum[mid] > point:
                hi = mid
            else:
                lo = mid + 1
        return self.keys[lo]


# Renders tried per slot: a street name owned by this cell, a building name of
# any form owned by this cell, then a "{street} {trade}" name on a street of
# this cell (unique by construction, since the street is).
STREET_NAME_ATTEMPTS = 4000
VENUE_OWNED_ATTEMPTS = 40
VENUE_STREET_ATTEMPTS = 24


def _draw_unique(kind: str, ctx: dict[str, Any], seed: int, used: set[str],
                 owners: NameOwners | None = None, here: tuple[int, int] | None = None,
                 attempts: int = STREET_NAME_ATTEMPTS) -> str:
    """One pool draw this cell owns that is not in ``used`` ("" when none turns up).

    Each slot has its own seeded stream, so what one slot draws never moves
    the draws of the slots after it.
    """
    from app import example_pools

    def accept(text: str) -> bool:
        if _norm_name(text) in used:
            return False
        return owners is None or here is None or owners.owner(kind, text) == here

    rng = random.Random(seed)
    drawn = example_pools.draw(kind, ctx, 1, rng, accept=accept, max_attempts=attempts)
    return drawn[0] if drawn else ""


def _street_candidates(plot: dict[str, Any], segs: list[dict[str, Any]], streets: list[str], limit: int = 6) -> list[str]:
    """The plot's own street first, then the named streets of this cell nearest its frontage."""
    out: list[str] = []
    seg_id = plot.get("seg")
    if seg_id is not None and 0 <= seg_id < len(segs) and segs[seg_id].get("name_id") is not None:
        out.append(streets[segs[seg_id]["name_id"]])
    front = plot.get("f") or [plot["r"][0], plot["r"][1]]
    fx, fy = int(front[0]), int(front[1])
    ranked = []
    for seg in segs:
        if seg.get("name_id") is None:
            continue
        dx = max(seg["x0"] - fx, 0, fx - seg["x1"])
        dy = max(seg["y0"] - fy, 0, fy - seg["y1"])
        ranked.append((dx + dy, seg["id"], streets[seg["name_id"]]))
    for _d, _id, name in sorted(ranked):
        if name not in out:
            out.append(name)
        if len(out) >= limit:
            break
    return out


def _name_streets(world: dict[str, Any], cell: dict[str, Any], segs: list[dict[str, Any]], ctx: dict[str, Any],
                  used: set[str], owners: NameOwners) -> list[str]:
    streets: list[str] = []
    base = _cell_seed(world, cell, _SALT_STREETS)
    here = (int(cell.get("x") or 0), int(cell.get("y") or 0))
    for seg in segs:
        length = abs(seg["x1"] - seg["x0"]) + abs(seg["y1"] - seg["y0"]) + 1
        if seg["cls"] == ROAD_ALLEY or length < 3:
            seg["name_id"] = None
            continue
        name = _draw_unique("street_name", ctx, (base << 12) ^ seg["id"], used, owners, here)
        if not name:
            seg["name_id"] = None
            continue
        used.add(_norm_name(name))
        seg["name_id"] = len(streets)
        streets.append(name)
    return streets


def _name_plots(world: dict[str, Any], city: dict[str, Any], cell: dict[str, Any], plots: list[dict[str, Any]],
                segs: list[dict[str, Any]], streets: list[str], ctx: dict[str, Any], used: set[str],
                owners: NameOwners) -> None:
    from app.venues import kind_label

    base = _cell_seed(world, cell, _SALT_NAMES)
    here = (int(cell.get("x") or 0), int(cell.get("y") or 0))
    for plot in plots:
        if plot.get("k") not in ("shop", "service", "temple") or not plot.get("vk"):
            continue
        if plot.get("name"):
            continue
        street = ""
        seg_id = plot.get("seg")
        if seg_id is not None and 0 <= seg_id < len(segs):
            name_id = segs[seg_id].get("name_id")
            if name_id is not None:
                street = streets[name_id]
        one = dict(ctx)
        one["venue_kind"] = plot["vk"]
        one["place_name"] = str(city.get("name") or "")
        if street:
            one["street_name"] = street
        one["street_form"] = False
        name = _draw_unique("venue_name", one, (base << 12) ^ int(plot["n"]), used, owners, here,
                            attempts=VENUE_OWNED_ATTEMPTS)
        if not name:
            for k, street_name in enumerate(_street_candidates(plot, segs, streets)):
                one = dict(one, street_name=street_name, street_form=True)
                name = _draw_unique("venue_name", one, (base << 16) ^ (int(plot["n"]) << 4) ^ k, used,
                                    attempts=VENUE_STREET_ATTEMPTS)
                if name:
                    break
        if not name:
            # Not seen in the probes; kept so a plot is never nameless.
            name = f"{street} {kind_label(plot['vk']).title()}".strip()
        used.add(_norm_name(name))
        plot["name"] = name


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


def generate_cell(
    world: dict[str, Any],
    city: dict[str, Any],
    cell: dict[str, Any],
    era: str,
    *,
    culture: str = "common",
    used_names: Iterable[str] = (),
    extra_joins: dict | None = None,
) -> dict[str, Any]:
    """One city cell's roads, segments, street names and plots. Pure.

    ``used_names`` are the names other generated cells of this city already
    hold; a draw that collides takes its slot's next draw. ``extra_joins`` is
    stored_edge_arrivals: roads an older stored neighbour already brings to a
    shared edge, which this cell meets (playtest #70).
    """
    side = _side(cell)
    era = str(era or "")
    roads, ports, shape = _skeleton_roads(world, city, cell, extra_joins)
    blocked = shape["blocked"]
    avenue = bytearray(side * side)
    for x, y in street_mask(int(cell.get("seed") or 1), side):
        avenue[y * side + x] = 1
    ward, stored = _wards(cell, side, avenue)
    params = _district_params(world, cell, stored, side)
    lm_tiles = metres_to_tiles(LANDMARK_METRES, side)
    reserved = bytearray(side * side)
    for index, district in enumerate(stored):
        if district.get("type") == "street":
            continue
        anchor = district.get("anchor") or [0, 0]
        ax, ay = clamp_int(int(anchor[0]), 0, side - 1), clamp_int(int(anchor[1]), 0, side - 1)
        reserved[ay * side + ax] = 1
        if district.get("type") in ("temple", "government", "military"):
            half = lm_tiles // 2
            for yy in range(max(0, ay - half), min(side, ay + half + 1)):
                for xx in range(max(0, ax - half), min(side, ax + half + 1)):
                    if ward[yy * side + xx] == index:
                        reserved[yy * side + xx] = 1
    # Side streets and alleys stop one tile short of a shared edge instead of
    # dead-ending on it; only the joins cross (playtest #70).
    for i in blocked:
        reserved[i] = 1
    _side_streets(roads, side, ward, params, reserved, blocked)
    _alleys(roads, side, ward, params, reserved)
    for i in blocked:
        roads[i] = ROAD_NONE
    _connect_all(roads, side, ports, blocked, shape["joins"])
    segs = _segments(roads, side, ward)
    hseg, vseg = _segment_index(segs, side)
    gates = [p for p in ports if p.get("gate")]
    plot_rng = random.Random(_cell_seed(world, cell, _SALT_PLOTS))
    core = _core_fn(city, cell, side)
    plots = _cut_plots(plot_rng, roads, side, ward, params, stored, gates, hseg, vseg, core)
    report = _assign_kinds(world, city, cell, stored, plots, roads, side, era, core)
    used = {_norm_name(name) for name in used_names if name}
    ctx = {"era": era or "preindustrial", "culture": culture or "common"}
    owners = NameOwners(world, city)
    streets = _name_streets(world, cell, segs, ctx, used, owners)
    _name_plots(world, city, cell, plots, segs, streets, ctx, used, owners)
    for plot in plots:
        if not plot.get("vk"):
            plot.pop("vk", None)
    return {
        "city_id": str(city.get("id") or ""),
        "cx": int(cell.get("x") or 0),
        "cy": int(cell.get("y") or 0),
        "local": [int((cell.get("local") or [0, 0])[0]), int((cell.get("local") or [0, 0])[1])],
        "side": side,
        "era": era,
        "gen_version": GEN_VERSION,
        "port_version": PORT_VERSION,
        "roads": roads,
        "segments": segs,
        "streets": streets,
        "plots": plots,
        "report": report,
    }


def plot_id(city_id: str, local: list[int] | tuple[int, int], n: int) -> str:
    return f"{city_id}.{int(local[0])}.{int(local[1])}.{int(n)}"


def parse_plot_id(value: str) -> tuple[str, int, int, int] | None:
    parts = str(value or "").strip().split(".")
    if len(parts) != 4:
        return None
    try:
        return parts[0], int(parts[1]), int(parts[2]), int(parts[3])
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Encoding and storage
# ---------------------------------------------------------------------------


def _pack(data: bytes) -> str:
    return base64.b64encode(zlib.compress(data, 6)).decode("ascii")


def _unpack(text: str) -> bytes:
    if not text:
        return b""
    return zlib.decompress(base64.b64decode(text.encode("ascii")))


def _compact_plot(plot: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in plot.items() if key != "id" and value not in (None, "", [])}


def encode_cell(town: dict[str, Any]) -> dict[str, Any]:
    """The town_cells column values for a generated cell (text, so saves carry them as JSON)."""
    plots = [_compact_plot(p) for p in town["plots"]]
    return {
        "city_id": town["city_id"],
        "gen_version": int(town["gen_version"]),
        "port_version": int(town["port_version"]),
        "side": int(town["side"]),
        "era": str(town.get("era") or ""),
        "roads": _pack(bytes(town["roads"])),
        "segments": _pack(json.dumps(town["segments"], separators=(",", ":")).encode("utf-8")),
        "streets": json.dumps(town["streets"], separators=(",", ":"), ensure_ascii=True),
        "plots": _pack(json.dumps(plots, separators=(",", ":"), ensure_ascii=True).encode("utf-8")),
    }


def decode_row(row: Any, local: list[int] | tuple[int, int] | None = None) -> dict[str, Any]:
    get = row.__getitem__
    side = int(get("side"))
    roads = bytearray(_unpack(str(get("roads") or "")))
    segs = json.loads(_unpack(str(get("segments") or "")) or b"[]")
    streets = json.loads(str(get("streets") or "[]"))
    plots = json.loads(_unpack(str(get("plots") or "")) or b"[]")
    city_id = str(get("city_id") or "")
    local = list(local) if local is not None else [0, 0]
    for plot in plots:
        plot["id"] = plot_id(city_id, local, int(plot["n"]))
    return {
        "map_id": str(get("map_id") or ""),
        "city_id": city_id,
        "cx": int(get("cx")),
        "cy": int(get("cy")),
        "local": local,
        "side": side,
        "era": str(get("era") or ""),
        "gen_version": int(get("gen_version")),
        "port_version": int(get("port_version")),
        "roads": roads,
        "segments": segs,
        "streets": streets,
        "plots": plots,
        "generated": True,
    }


def ensure_tables(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS town_cells (
          map_id TEXT NOT NULL, cx INTEGER NOT NULL, cy INTEGER NOT NULL, city_id TEXT NOT NULL,
          gen_version INTEGER NOT NULL, port_version INTEGER NOT NULL, side INTEGER NOT NULL,
          era TEXT NOT NULL DEFAULT '', roads TEXT NOT NULL, segments TEXT NOT NULL,
          streets TEXT NOT NULL, plots TEXT NOT NULL,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (map_id, cx, cy)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS town_seen (
          id INTEGER PRIMARY KEY AUTOINCREMENT, map_id TEXT NOT NULL, cx INTEGER NOT NULL,
          cy INTEGER NOT NULL, roads TEXT NOT NULL DEFAULT '', plots TEXT NOT NULL DEFAULT '',
          told TEXT NOT NULL DEFAULT '', turn INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS town_seen_cell ON town_seen (map_id, cx, cy)")


def _db_key(conn) -> str:
    try:
        row = conn.execute("PRAGMA database_list").fetchone()
        return str(row[2] or "")
    except Exception:
        return ""


def _locate(chart: dict[str, Any], cx: int, cy: int) -> tuple[dict[str, Any], dict[str, Any]] | None:
    index = chart.get("cell_index")
    if not isinstance(index, dict):
        from app.world_scale import index_cities

        index = index_cities(chart.get("cities") or [])
        chart["cell_index"] = index
    found = index.get(f"{int(cx)},{int(cy)}")
    if not isinstance(found, dict):
        return None
    return found.get("city") or {}, found.get("cell") or {}


def _row_signature(conn, map_id: str, cx: int, cy: int):
    return conn.execute(
        "SELECT rowid, created_at, gen_version, length(plots) AS size FROM town_cells WHERE map_id = ? AND cx = ? AND cy = ?",
        (map_id, int(cx), int(cy)),
    ).fetchone()


def stored_cell(conn, chart: dict[str, Any], cx: int, cy: int) -> dict[str, Any] | None:
    """The stored row of a cell, decoded (cached), or None. Never generates."""
    map_id = str(chart.get("id") or "")
    sig_row = _row_signature(conn, map_id, cx, cy)
    if sig_row is None:
        return None
    sig = (int(sig_row["rowid"]), str(sig_row["created_at"]), int(sig_row["gen_version"]), int(sig_row["size"] or 0))
    key = (_db_key(conn), map_id, int(cx), int(cy))
    cached = _CELL_CACHE.get(key)
    if cached is not None and cached[0] == sig:
        return cached[1]
    row = conn.execute(
        "SELECT * FROM town_cells WHERE map_id = ? AND cx = ? AND cy = ?", (map_id, int(cx), int(cy))
    ).fetchone()
    if row is None:
        return None
    located = _locate(chart, cx, cy)
    local = (located[1].get("local") if located else None) or [0, 0]
    decoded = decode_row(row, local)
    _CELL_CACHE.put(key, (sig, decoded))
    return decoded


def _world_name_context(conn) -> dict[str, Any]:
    from app import example_pools

    options: dict[str, Any] = {}
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = 'playthrough_options'").fetchone()
        if row:
            loaded = json.loads(row["value"])
            if isinstance(loaded, dict):
                options = loaded
    except Exception:
        options = {}
    return example_pools.world_context(options)


def city_used_names(conn, map_id: str, city_id: str, *, skip: tuple[int, int] | None = None,
                    other_versions_only: bool = True) -> set[str]:
    """Names stored in this city's generated cells.

    Within one GEN_VERSION, NameOwners already keeps every name in one cell, so
    by default only rows of another version are read: those were named under
    other rules and may hold a name this version would give a different cell.
    """
    used: set[str] = set()
    query = "SELECT cx, cy, streets, plots FROM town_cells WHERE map_id = ? AND city_id = ?"
    params: tuple = (map_id, city_id)
    if other_versions_only:
        query += " AND gen_version != ?"
        params = (map_id, city_id, GEN_VERSION)
    for row in conn.execute(query, params).fetchall():
        if skip is not None and (int(row["cx"]), int(row["cy"])) == skip:
            continue
        for name in json.loads(str(row["streets"] or "[]")):
            used.add(_norm_name(name))
        for plot in json.loads(_unpack(str(row["plots"] or "")) or b"[]"):
            if plot.get("name"):
                used.add(_norm_name(plot["name"]))
    return used


def stored_edge_arrivals(conn, chart: dict[str, Any], city: dict[str, Any],
                         cell: dict[str, Any]) -> dict[tuple[tuple[int, int], str], list[float]]:
    """Roads that stored neighbours of an older GEN_VERSION bring to their shared edge with ``cell``.

    Keyed (neighbour cell, neighbour edge) -> metres along the edge, for
    edge_joins. A v1 row was laid without joins, so most of its edge roads
    dead-end (playtest #70: 4 of 5 on Harmere's north edge); the new cell
    lays a road to meet each one. Rows of this version already agree with
    edge_joins and add nothing, so generation order does not matter.
    """
    out: dict[tuple[tuple[int, int], str], list[float]] = {}
    cells = _city_cells(city)
    cx, cy = int(cell.get("x") or 0), int(cell.get("y") or 0)
    for edge, (dx, dy) in _EDGE_STEP.items():
        nb = (cx + dx, cy + dy)
        if nb not in cells:
            continue
        try:
            town = stored_cell(conn, chart, nb[0], nb[1])
        except Exception:
            town = None
        if town is None or int(town.get("gen_version") or 0) >= GEN_VERSION:
            continue
        nside = int(town["side"])
        nedge = _OPPOSITE[edge]
        ks = set(edge_arrivals(town["roads"], nside, nedge))
        for port in city_ports(chart, city).get(nb, []):
            if port.get("to") and (int(port["to"][0]), int(port["to"][1])) == (cx, cy):
                px, py = port_tile(port, nside)
                if town["roads"][py * nside + px]:
                    ks.add(px if nedge in ("N", "S") else py)
        if ks:
            out[(nb, nedge)] = [(k + 0.5) * tile_metres(nside) for k in sorted(ks)]
    return out


def get_cell(conn, chart: dict[str, Any], cx: int, cy: int, *, create: bool = False) -> dict[str, Any] | None:
    """A city cell's town grid: the stored row, or (with ``create``) generated and stored now.

    A stored row is returned as it is, whatever its gen_version. Only turn and
    walk code may pass ``create``; read routes never do.
    """
    found = stored_cell(conn, chart, cx, cy)
    if found is not None or not create:
        return found
    if str(chart.get("scale") or "") != "world":
        return None
    located = _locate(chart, cx, cy)
    if not located:
        return None
    city, cell = located
    ensure_tables(conn)
    ctx = _world_name_context(conn)
    map_id = str(chart.get("id") or "")
    city_id = str(city.get("id") or "")
    used = city_used_names(conn, map_id, city_id)
    town = generate_cell(chart, city, cell, str(ctx.get("era") or ""), culture=str(ctx.get("culture") or "common"),
                         used_names=used, extra_joins=stored_edge_arrivals(conn, chart, city, cell))
    cols = encode_cell(town)
    conn.execute(
        "INSERT OR IGNORE INTO town_cells (map_id, cx, cy, city_id, gen_version, port_version, side, era, roads, segments, streets, plots) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (map_id, int(cx), int(cy), cols["city_id"], cols["gen_version"], cols["port_version"], cols["side"], cols["era"],
         cols["roads"], cols["segments"], cols["streets"], cols["plots"]),
    )
    return stored_cell(conn, chart, cx, cy)


# ---------------------------------------------------------------------------
# What the player has seen (town_seen, append-only)
# ---------------------------------------------------------------------------


def _bits_encode(bits: bytearray) -> str:
    return _pack(bytes(bits)) if any(bits) else ""


def _bits_decode(text: str, nbits: int) -> bytearray:
    raw = bytearray(_unpack(text)) if text else bytearray()
    need = (nbits + 7) // 8
    if len(raw) < need:
        raw.extend(bytes(need - len(raw)))
    return raw


def _bit(bits: bytearray, i: int) -> bool:
    return bool(bits[i >> 3] & (1 << (i & 7)))


def _set_bit(bits: bytearray, i: int) -> None:
    bits[i >> 3] |= 1 << (i & 7)


def fold_seen(conn, map_id: str, cx: int, cy: int, side: int, nplots: int = 0) -> dict[str, Any]:
    """Everything the player has seen of a cell: the OR of its town_seen rows."""
    roads = bytearray((side * side + 7) // 8)
    plots = bytearray((max(nplots, 1) + 7) // 8)
    told: list[Any] = []
    try:
        rows = conn.execute(
            "SELECT roads, plots, told FROM town_seen WHERE map_id = ? AND cx = ? AND cy = ? ORDER BY id",
            (map_id, int(cx), int(cy)),
        ).fetchall()
    except Exception:
        rows = []
    for row in rows:
        if row["roads"]:
            other = _bits_decode(str(row["roads"]), side * side)
            for k in range(len(roads)):
                roads[k] |= other[k]
        if row["plots"]:
            other = _bits_decode(str(row["plots"]), 0)
            if len(other) > len(plots):
                plots.extend(bytes(len(other) - len(plots)))
            for k in range(len(other)):
                plots[k] |= other[k]
        if row["told"]:
            try:
                for item in json.loads(str(row["told"])):
                    if item not in told:
                        told.append(item)
            except (TypeError, ValueError):
                pass
    return {"roads": roads, "plots": plots, "told": told}


def record_seen(conn, map_id: str, cx: int, cy: int, side: int, *, road_tiles: Iterable[int] = (),
                plot_ns: Iterable[int] = (), told: Iterable[Any] = (), turn: int = 0) -> int | None:
    """Append one town_seen row with only the newly seen bits; None when nothing is new."""
    plot_list = sorted({int(n) for n in plot_ns})
    current = fold_seen(conn, map_id, cx, cy, side, (plot_list[-1] + 1) if plot_list else 0)
    new_roads = bytearray(len(current["roads"]))
    any_road = False
    for i in road_tiles:
        i = int(i)
        if 0 <= i < side * side and not _bit(current["roads"], i):
            _set_bit(new_roads, i)
            any_road = True
    new_plots = bytearray((plot_list[-1] + 8) // 8) if plot_list else bytearray()
    any_plot = False
    for n in plot_list:
        if n >= 0 and not (n >> 3 < len(current["plots"]) and _bit(current["plots"], n)):
            _set_bit(new_plots, n)
            any_plot = True
    new_told = [item for item in dict.fromkeys(told) if item not in current["told"]]
    if not (any_road or any_plot or new_told):
        return None
    cursor = conn.execute(
        "INSERT INTO town_seen (map_id, cx, cy, roads, plots, told, turn) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (map_id, int(cx), int(cy), _bits_encode(new_roads) if any_road else "",
         _bits_encode(new_plots) if any_plot else "", json.dumps(new_told) if new_told else "", int(turn)),
    )
    return int(cursor.lastrowid)


# ---------------------------------------------------------------------------
# Read API (never generates, never writes)
# ---------------------------------------------------------------------------


def _seen_world_cells(chart: dict[str, Any]) -> set[str]:
    seen = {str(v) for v in (chart.get("visited") or [])} | {str(v) for v in (chart.get("revealed") or [])}
    player = chart.get("player") or {}
    seen.add(f"{int(player.get('x') or 0)},{int(player.get('y') or 0)}")
    return seen


def town_position(conn) -> dict[str, Any] | None:
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = 'town_position'").fetchone()
    except Exception:
        return None
    if not row:
        return None
    try:
        value = json.loads(row["value"])
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _known_city(chart: dict[str, Any], city_id: str) -> dict[str, Any] | None:
    from app.tile_world import filter_settlements_for_player

    cities = {str(c.get("id") or ""): c for c in chart.get("cities") or [] if isinstance(c, dict)}
    if city_id not in cities:
        return None
    known = {str(item.get("id") or "") for item in filter_settlements_for_player(chart)}
    player = chart.get("player") or {}
    located = _locate(chart, int(player.get("x") or 0), int(player.get("y") or 0))
    if located and str(located[0].get("id") or "") == city_id:
        known.add(city_id)
    return cities[city_id] if city_id in known else None


def _realized(conn, map_city: str) -> dict[str, dict[str, Any]]:
    try:
        rows = conn.execute(
            "SELECT code, plot_id, keeper_npc_id FROM locations WHERE plot_id LIKE ?", (f"{map_city}.%",)
        ).fetchall()
    except Exception:
        return {}
    return {str(r["plot_id"]): {"code": str(r["code"] or ""), "keeper_npc_id": int(r["keeper_npc_id"] or 0)} for r in rows}


def _world_minute(conn) -> int:
    try:
        row = conn.execute("SELECT value FROM pacing WHERE key = 'world_minute'").fetchone()
        return int(float(row["value"])) if row else 0
    except Exception:
        return 0


def _plot_label(plot: dict[str, Any]) -> str:
    from app.venues import kind_label

    if plot.get("vk"):
        return kind_label(str(plot["vk"]))
    return str(plot.get("k") or "").replace("_", " ")


def _told_plot_ns(town: dict[str, Any], told: list[Any]) -> set[int]:
    out: set[int] = set()
    stall_ids = {str(p.get("st")): int(p["n"]) for p in town["plots"] if p.get("st")}
    notice_ids: dict[str, int] = {}
    for p in town["plots"]:
        for nid in p.get("nt") or []:
            notice_ids[str(nid)] = int(p["n"])
    for item in told:
        if isinstance(item, int):
            out.add(item)
        elif isinstance(item, str) and item.startswith("stall:") and item[6:] in stall_ids:
            out.add(stall_ids[item[6:]])
        elif isinstance(item, str) and item.startswith("notice:") and item[7:] in notice_ids:
            out.add(notice_ids[item[7:]])
    return out


def _segment_tiles(seg: dict[str, Any], side: int) -> Iterable[int]:
    for yy in range(seg["y0"], seg["y1"] + 1):
        for xx in range(seg["x0"], seg["x1"] + 1):
            yield yy * side + xx


def town_era(conn) -> str:
    try:
        return str(_world_name_context(conn).get("era") or "")
    except Exception:
        return ""


def _gate_items(world: dict[str, Any], city: dict[str, Any], cell: dict[str, Any], town: dict[str, Any],
                walls: dict[str, Any]) -> list[dict[str, Any]]:
    """Every gate of a generated cell: gate plots, and gates with no plot (a
    stored cell whose gate square did not fit, a walled town's avenue gates),
    drawn from their tiles (playtest #71)."""
    side = int(town["side"])
    out = []
    plotted: set[tuple[int, int]] = set()
    for p in town["plots"]:
        if p.get("k") == "gate":
            out.append({"plot": p["id"], "label": p.get("name") or "", "gate": p.get("gate"), "f": p.get("f")})
            if p.get("f"):
                plotted.add((int(p["f"][0]), int(p["f"][1])))
    for item in cell_exits(world, city, cell, town["roads"], walls):
        if item["kind"] != "gate" or (item["x"], item["y"]) in plotted:
            continue
        if any(p.get("f") and abs(int(p["f"][0]) - item["x"]) + abs(int(p["f"][1]) - item["y"]) <= 2
               for p in town["plots"] if p.get("k") == "gate"):
            continue
        out.append({"label": item.get("label") or "", "gate": item.get("gate"), "x": item["x"], "y": item["y"],
                    "edge": item["edge"]})
    return out


def _cell_view(conn, chart: dict[str, Any], city: dict[str, Any], cell: dict[str, Any], position: dict[str, Any] | None,
               minute: int, realized: dict[str, dict[str, Any]], notices_meta: dict[str, dict[str, Any]],
               walls: dict[str, Any] | None = None) -> dict[str, Any]:
    from app.venues import describe_hours, default_hours, is_open

    cx, cy = int(cell.get("x") or 0), int(cell.get("y") or 0)
    side = _side(cell)
    local = [int((cell.get("local") or [0, 0])[0]), int((cell.get("local") or [0, 0])[1])]
    town = stored_cell(conn, chart, cx, cy)
    out: dict[str, Any] = {"cx": cx, "cy": cy, "local": local, "side": side, "known": True,
                           "outer": outer_edges(city, cx, cy)}
    if walls is None:
        walls = town_walls(chart, city, town_era(conn))
    if town is None:
        sk = skeleton(chart, city, cell, stored_edge_arrivals(conn, chart, city, cell))
        out["generated"] = False
        out["roads"] = _pack(bytes(sk["roads"]))
        out["segments"] = [
            {k: seg[k] for k in ("id", "cls", "x0", "y0", "x1", "y1")} for seg in sk["segments"]
        ]
        out["plots"] = []
        out["gates"] = [
            {"edge": p["edge"], "t": p["t"], "gate": p["gate"], "label": p.get("label") or "",
             "x": port_tile(p, side)[0], "y": port_tile(p, side)[1]}
            for p in sk["ports"] if p.get("gate")
        ]
        out["notices"] = []
        return out
    map_id = str(chart.get("id") or "")
    seen = fold_seen(conn, map_id, cx, cy, side, len(town["plots"]))
    roads = town["roads"]
    visible = bytearray(side * side)
    for i in range(side * side):
        cls = roads[i]
        if cls in (ROAD_AVENUE, ROAD_MAIN) or (cls and _bit(seen["roads"], i)):
            visible[i] = cls
    told = _told_plot_ns(town, seen["told"])
    here_plot = str((position or {}).get("plot") or "") if position and int(position.get("cx", -1)) == cx and int(position.get("cy", -1)) == cy else ""
    segments = []
    for seg in town["segments"]:
        tiles = list(_segment_tiles(seg, side))
        if not any(visible[i] for i in tiles):
            continue
        item = {k: seg[k] for k in ("id", "cls", "x0", "y0", "x1", "y1")}
        if seg.get("name_id") is not None and any(_bit(seen["roads"], i) for i in tiles):
            item["name"] = town["streets"][seg["name_id"]]
        segments.append(item)
    plots = []
    notices = []
    for plot in town["plots"]:
        n = int(plot["n"])
        pid = plot["id"]
        read = (n >> 3) < len(seen["plots"]) and _bit(seen["plots"], n)
        front = plot.get("f")
        front_seen = bool(front) and _bit(seen["roads"], front[1] * side + front[0])
        is_realized = pid in realized
        if not (plot.get("k") == "gate" or read or front_seen or n in told or is_realized):
            continue
        item: dict[str, Any] = {"id": pid, "r": plot["r"], "k": plot.get("k"), "label": _plot_label(plot)}
        if plot.get("vk"):
            item["vk"] = plot["vk"]
            hours = default_hours(str(plot["vk"]))
            item["hours"] = describe_hours(*hours)
            item["open"] = bool(is_open(hours[0], hours[1], minute))
        if plot.get("name") and (plot.get("k") == "gate" or read or n in told or is_realized):
            item["name"] = plot["name"]
        if front:
            item["f"] = front
        item["here"] = pid == here_plot
        if is_realized:
            item["realized"] = realized[pid]["code"]
        plots.append(item)
        for nid in plot.get("nt") or []:
            meta = notices_meta.get(str(nid)) or {}
            notices.append({"id": nid, "kind": str(meta.get("kind") or ""), "label": str(meta.get("label") or ""),
                            "plot": pid})
    out.update(
        {
            "generated": True,
            "era": town["era"],
            "gen_version": town["gen_version"],
            "roads": _pack(bytes(visible)),
            "segments": segments,
            "plots": plots,
            "gates": _gate_items(chart, city, cell, town, walls),
            "notices": notices,
        }
    )
    if position and (int(position.get("cx", -1)), int(position.get("cy", -1))) == (cx, cy):
        # Where the player can step out of town from this cell (the Leave control).
        out["exits"] = [[e["x"], e["y"], e["edge"]] for e in cell_exits(chart, city, cell, town["roads"], walls)]
    return out


def town_view(conn, chart: dict[str, Any] | None, *, city_id: str = "", cx: int | None = None, cy: int | None = None,
              r: int = 1) -> dict[str, Any]:
    """The street view of one city cell and its city neighbours within ``r``. Read-only.

    Raises ValueError for ``r`` above MAX_VIEW_RADIUS (the route answers 400).
    """
    r = int(r)
    if r < 0 or r > MAX_VIEW_RADIUS:
        raise ValueError(f"r must be 0..{MAX_VIEW_RADIUS}")
    if not chart or str(chart.get("scale") or "") != "world" or not chart.get("cities"):
        return {"available": False, "reason": "This map has no town grids.", "cells": []}
    player = chart.get("player") or {}
    px, py = int(player.get("x") or 0), int(player.get("y") or 0)
    here = _locate(chart, px, py)
    wanted = str(city_id or "").strip() or (str(here[0].get("id") or "") if here else "")
    if not wanted:
        return {"available": False, "reason": "You are not in a settlement.", "cells": []}
    city = _known_city(chart, wanted)
    if city is None:
        return {"available": False, "reason": "You know of no such settlement.", "cells": []}
    cells = _city_cells(city)
    if cx is None or cy is None:
        if here and str(here[0].get("id") or "") == wanted:
            cx, cy = px, py
        else:
            cx, cy = int(city.get("x") or 0), int(city.get("y") or 0)
    if (int(cx), int(cy)) not in cells:
        return {"available": False, "reason": "That cell is not part of this settlement.", "cells": []}
    seen_cells = _seen_world_cells(chart)
    position = town_position(conn)
    minute = _world_minute(conn) % (24 * 60)
    realized = _realized(conn, wanted)
    walls = town_walls(chart, city, town_era(conn))
    notices_meta: dict[str, dict[str, Any]] = {}
    for one in cells.values():
        for notice in one.get("notices") or []:
            if isinstance(notice, dict) and notice.get("id"):
                notices_meta[str(notice["id"])] = notice
    out_cells = []
    for yy in range(int(cy) - r, int(cy) + r + 1):
        for xx in range(int(cx) - r, int(cx) + r + 1):
            cell = cells.get((xx, yy))
            if cell is None:
                continue
            if f"{xx},{yy}" not in seen_cells:
                local = cell.get("local") or [0, 0]
                out_cells.append({"cx": xx, "cy": yy, "local": [int(local[0]), int(local[1])], "side": _side(cell),
                                  "known": False, "outer": outer_edges(city, xx, yy)})
                continue
            out_cells.append(_cell_view(conn, chart, city, cell, position, minute, realized, notices_meta, walls))
    pos_out = None
    if position and str(position.get("city_id") or "") == wanted:
        pos_out = {k: position.get(k) for k in ("cx", "cy", "fx", "fy", "plot", "inside", "heading")}
    return {
        "available": True,
        "city_id": wanted,
        "name": str(city.get("name") or ""),
        "band": str(city.get("band") or ""),
        "center": {"cx": int(cx), "cy": int(cy)},
        "r": r,
        "walled": bool(walls.get("walled")),
        "wall_kind": str(walls.get("kind") or ""),
        "cells": out_cells,
        "player": pos_out,
        "road_classes": {str(k): v for k, v in ROAD_CLASS_NAMES.items()},
    }


def plot_peek(conn, chart: dict[str, Any] | None, plot_ref: str) -> dict[str, Any] | None:
    """What the player knows of one plot, or None when they do not know it (the route answers 404)."""
    from app.venues import default_hours, describe_hours, is_open

    parsed = parse_plot_id(plot_ref)
    if parsed is None or not chart or str(chart.get("scale") or "") != "world":
        return None
    city_id, lx, ly, n = parsed
    city = _known_city(chart, city_id)
    if city is None:
        return None
    cell = next(
        (c for c in _city_cells(city).values() if [int(v) for v in (c.get("local") or [0, 0])] == [lx, ly]), None
    )
    if cell is None:
        return None
    cx, cy = int(cell.get("x") or 0), int(cell.get("y") or 0)
    if f"{cx},{cy}" not in _seen_world_cells(chart):
        return None
    view = _cell_view(conn, chart, city, cell, town_position(conn), _world_minute(conn) % (24 * 60),
                      _realized(conn, city_id), {})
    item = next((p for p in view.get("plots") or [] if p["id"] == plot_ref), None)
    if item is None:
        return None
    town = stored_cell(conn, chart, cx, cy)
    plot = town["plots"][n] if town and 0 <= n < len(town["plots"]) else {}
    street = ""
    seg_id = plot.get("seg")
    if seg_id is not None and town and 0 <= seg_id < len(town["segments"]):
        seg = town["segments"][seg_id]
        visible_names = {s["id"]: s.get("name") for s in view.get("segments") or []}
        street = str(visible_names.get(seg_id) or "")
    districts = [d for d in cell.get("districts") or [] if isinstance(d, dict)]
    d = int(plot.get("d", -1))
    ward = districts[d] if 0 <= d < len(districts) else {}
    out = {
        "id": plot_ref,
        "city_id": city_id,
        "cx": cx,
        "cy": cy,
        "name": item.get("name") or "",
        "kind": item.get("k"),
        "label": item.get("label") or "",
        "street": street,
        "ward": str(ward.get("name") or ""),
        "ward_type": str(ward.get("type") or ""),
        "realized": bool(item.get("realized")),
        "code": item.get("realized") or "",
        "here": bool(item.get("here")),
        "keeper": "",
    }
    if plot.get("vk"):
        hours = default_hours(str(plot["vk"]))
        out["hours"] = describe_hours(*hours)
        out["open"] = bool(is_open(hours[0], hours[1], _world_minute(conn) % (24 * 60)))
    if out["realized"]:
        try:
            row = conn.execute(
                "SELECT n.name FROM locations l JOIN npcs n ON n.id = l.keeper_npc_id WHERE l.plot_id = ?", (plot_ref,)
            ).fetchone()
            out["keeper"] = str(row["name"]) if row else ""
        except Exception:
            out["keeper"] = ""
    return out


def settlement_town_block(conn, chart: dict[str, Any] | None, view: dict[str, Any]) -> dict[str, Any]:
    """The ``town`` block of GET /api/tiles/map/settlement; puts the marker on the real fine tile."""
    settlement = view.get("settlement") if isinstance(view, dict) else None
    zoomable = bool(
        chart and str(chart.get("scale") or "") == "world" and isinstance(settlement, dict)
        and int(settlement.get("known_cells") or 0) > 0
    )
    position = town_position(conn)
    player = None
    if position and isinstance(settlement, dict) and str(position.get("city_id") or "") == str(settlement.get("id") or ""):
        player = {k: position.get(k) for k in ("cx", "cy", "fx", "fy", "plot")}
        marker = settlement.get("player")
        if isinstance(marker, dict) and int(marker.get("x", -1)) == int(position.get("cx", -2)) and int(marker.get("y", -1)) == int(position.get("cy", -2)):
            marker["fine_x"] = int(position.get("fx") or 0)
            marker["fine_y"] = int(position.get("fy") or 0)
    return {"zoomable": zoomable, "player": player}


# ---------------------------------------------------------------------------
# Saves
# ---------------------------------------------------------------------------


def campaign_town_rows(conn, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """town_cells / town_seen rows a save carries: those of the campaign's maps (#25)."""
    from app.tile_world import campaign_map_ids

    keep = campaign_map_ids(conn)
    if not keep:
        return rows
    return [row for row in rows if str((row or {}).get("map_id") or "") in keep]


def prune_town_rows(conn, keep: set[str]) -> int:
    """Drop town rows of maps not in ``keep``."""
    removed = 0
    if not keep:
        return 0
    marks = ", ".join("?" for _ in keep)
    for table in ("town_cells", "town_seen"):
        try:
            cursor = conn.execute(f"DELETE FROM {table} WHERE map_id NOT IN ({marks})", sorted(keep))
            removed += int(cursor.rowcount or 0)
        except Exception:
            pass
    return removed


# ---------------------------------------------------------------------------
# Debug
# ---------------------------------------------------------------------------

_GLYPH = {
    "shop": "$", "service": "&", "house": "h", "yard": ".", "temple": "T", "office": "O", "barracks": "B",
    "warehouse": "w", "square": "+", "gate": "G", "empty": "_", "field": ",", "pasture": "~", "orchard": "o",
}


def ascii_render(town: dict[str, Any], *, x0: int = 0, y0: int = 0, width: int | None = None, height: int | None = None) -> str:
    """A text picture of a generated cell: roads by class, plots by kind (debug and probes)."""
    side = int(town["side"])
    grid = [[" "] * side for _ in range(side)]
    for plot in town["plots"]:
        x, y, w, h = plot["r"]
        glyph = _GLYPH.get(str(plot.get("k") or ""), "?")
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                grid[yy][xx] = glyph
    road_glyph = {ROAD_AVENUE: "#", ROAD_MAIN: "=", ROAD_STREET: "-", ROAD_ALLEY: ":"}
    roads = town["roads"]
    for i in range(side * side):
        if roads[i]:
            grid[i // side][i % side] = road_glyph.get(roads[i], "?")
    width = width or side
    height = height or side
    return "\n".join("".join(row[x0:x0 + width]) for row in grid[y0:y0 + height])
