"""
The player inside a town (docs/TownGrid.md, slice B).

Slice A (app/town_grid.py) lays roads and plots over every city cell's fine
grid. This module stands the player on a road tile of that grid and keeps the
prose and the state agreeing about where they are:

* ``town_position`` (a settings row, snapshotted) holds the fine tile; while it
  is present the world-map marker is on its cell.
* Walks follow the roads, cost in-game minutes per tile, stop at the turn's
  budget and reveal what is in sight.
* What the player types ("go to the bakery", "back to the Crooked Lantern",
  "head to Wheel Street", "out the north gate") resolves to a plot, a street or
  a gate before the prompt is built, so the draft is told where the walk ends.
* A plot becomes a ``locations`` row only when the player goes in, or a
  planned workplace is realized. Nothing here invents a building that is not
  on the grid (playtest #55).

Order inside a turn (TownGrid.md 5.1): ``plan_turn`` runs in play_turn before
the prompt and writes only ``town_cells`` cache rows; ``resolve_town_movement``
(inside resolve_movement, before the rewind snapshot) only edits the turn
dict; ``apply_town_turn`` runs after the snapshot, so the rows it appends are
removed by an ordinary rewind and ``town_position`` is restored by key.
"""
from __future__ import annotations

import json
import math
import re
from collections import deque
from typing import Any, Iterable

from app import town_grid as tg
from app import venues

POSITION_KEY = "town_position"
SIGHT_METRES = 40
READ_METRES = 15
AHEAD_METRES = 150
NEAR_METRES = 20
AROUND_MINUTES = 3
PLACES_MAX = 8
SMALL_CITY_CELLS = 5
MAX_CELLS_PER_TURN = 5

_N4 = ((0, -1), (1, 0), (0, 1), (-1, 0))
_EDGE_FROM_STEP = {(1, 0): "W", (-1, 0): "E", (0, 1): "N", (0, -1): "S"}
_EDGE_COMPASS = {"N": "north", "E": "east", "S": "south", "W": "west"}
_COMPASS_EDGE = {v: k for k, v in _EDGE_COMPASS.items()}
_HEADING_STEP = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}
_NAMED_KINDS = frozenset({"shop", "service", "temple", "office", "barracks", "gate"})
_DOOR_KINDS = frozenset({"shop", "service", "temple"})

# Leaving the town: "leave town", "out of the city", "out the north gate".
_LEAVE_RE = re.compile(
    r"\b(?:leave|leaving|exit|exiting|out\s+of)\s+(?:the\s+)?(?:town|city|village|hamlet|settlement|walls)\b"
    r"|\b(?:out|through|via)\s+(?:the\s+)?(?:(?:north|south|east|west)(?:ern)?\s+)?gates?\b",
    re.I,
)
# Words just before a leave that say the player is not leaving: playtest #71,
# "i cant leave the city due to a game bug" walked the player out of town.
_LEAVE_NOT_RE = re.compile(
    r"\b(?:can'?t|cannot|can\s+not|couldn'?t|could\s+not|unable\s+to|won'?t|will\s+not|wouldn'?t|don'?t|do\s+not|"
    r"didn'?t|did\s+not|never|not|no\s+way\s+to|isn'?t\s+letting\s+me|not\s+allowed\s+to|stops?\s+me\s+from|"
    r"stuck|trapped|before\s+i|instead\s+of|rather\s+than|without)\b[\w\s']{0,24}$",
    re.I,
)
_STEP_EDGE = {(0, -1): "N", (1, 0): "E", (0, 1): "S", (-1, 0): "W"}
# Walking up to a gate without going out of it.
_TO_GATE_RE = re.compile(
    r"\b(?:to|for|toward|towards|by|at)\s+(?:the\s+)?(?:(?:north|south|east|west)(?:ern)?\s+)?gates?\b", re.I
)
_GATE_COMPASS_RE = re.compile(r"\b(?P<compass>north|south|east|west)(?:ern)?\s+gates?\b", re.I)
# A line that heads somewhere even when the intent table does not call it travel.
_GO_RE = re.compile(
    r"\b(?:go|goes|going|head|heads|heading|walk|walks|walking|find|look\s+for|visit|make\s+(?:my|our)\s+way|"
    r"return|back\s+to|follow|take\s+me|wander|stroll|hurry|run)\b",
    re.I,
)
# "the market" with no ward name: the nearest market ward.
_WARD_WORDS = {"market": "shopping", "bazaar": "shopping", "marketplace": "shopping"}


# ---------------------------------------------------------------------------
# The chart, the city and the position
# ---------------------------------------------------------------------------


def world_chart(conn) -> dict[str, Any] | None:
    """The active world-scale chart with cities, or None (legacy maps have no towns)."""
    from app.tile_world import get_map

    try:
        chart = get_map(None, conn=conn)
    except Exception:
        return None
    if not chart or str(chart.get("scale") or "") != "world" or not chart.get("cities"):
        return None
    return chart


def player_cell(chart: dict[str, Any]) -> tuple[int, int]:
    player = chart.get("player") or {}
    return int(player.get("x") or 0), int(player.get("y") or 0)


def city_by_id(chart: dict[str, Any], city_id: str) -> dict[str, Any] | None:
    for city in chart.get("cities") or []:
        if isinstance(city, dict) and str(city.get("id") or "") == str(city_id or ""):
            return city
    return None


def get_position(conn) -> dict[str, Any] | None:
    return tg.town_position(conn)


def write_position(conn, pos: dict[str, Any]) -> None:
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (POSITION_KEY, json.dumps(pos, ensure_ascii=True, separators=(",", ":"))),
    )


def clear_position(conn) -> None:
    conn.execute("DELETE FROM settings WHERE key = ?", (POSITION_KEY,))


def _make_position(chart: dict[str, Any], city: dict[str, Any], cx: int, cy: int, town: dict[str, Any], i: int,
                   *, heading: str = "", inside: str = "") -> dict[str, Any]:
    side = int(town["side"])
    return {
        "map_id": str(chart.get("id") or ""),
        "city_id": str(city.get("id") or ""),
        "cx": int(cx),
        "cy": int(cy),
        "fx": int(i % side),
        "fy": int(i // side),
        "plot": _frontage_plot_id(town, i),
        "inside": str(inside or ""),
        "heading": str(heading or ""),
    }


def _pos_index(pos: dict[str, Any], side: int) -> int:
    return int(pos.get("fy") or 0) * int(side) + int(pos.get("fx") or 0)


# ---------------------------------------------------------------------------
# Per-cell indices (kept on the decoded, cached row)
# ---------------------------------------------------------------------------


def _ix(town: dict[str, Any]) -> dict[str, Any]:
    ix = town.get("_ix")
    if ix is None:
        side = int(town["side"])
        front: dict[int, list[dict[str, Any]]] = {}
        for plot in town["plots"]:
            f = plot.get("f")
            if f:
                front.setdefault(int(f[1]) * side + int(f[0]), []).append(plot)
        hseg, vseg = tg._segment_index(town["segments"], side)
        ix = {"front": front, "hseg": hseg, "vseg": vseg}
        town["_ix"] = ix
    return ix


def _frontage_plot(town: dict[str, Any], i: int) -> dict[str, Any] | None:
    plots = _ix(town)["front"].get(int(i)) or []
    if not plots:
        return None
    # A named door first: the inn rather than the yard behind it.
    return sorted(plots, key=lambda p: (0 if p.get("k") in _DOOR_KINDS else 1 if p.get("name") else 2, int(p["n"])))[0]


def _frontage_plot_id(town: dict[str, Any], i: int) -> str:
    plot = _frontage_plot(town, i)
    return str(plot["id"]) if plot else ""


def street_at(town: dict[str, Any], i: int) -> str:
    ix = _ix(town)
    for sid in (ix["hseg"][i], ix["vseg"][i]):
        if sid is not None and sid >= 0:
            seg = town["segments"][sid]
            nid = seg.get("name_id")
            if nid is not None and 0 <= int(nid) < len(town["streets"]):
                return str(town["streets"][int(nid)])
    return ""


def _plot_street(town: dict[str, Any], plot: dict[str, Any]) -> str:
    seg_id = plot.get("seg")
    if seg_id is not None and 0 <= int(seg_id) < len(town["segments"]):
        nid = town["segments"][int(seg_id)].get("name_id")
        if nid is not None and 0 <= int(nid) < len(town["streets"]):
            return str(town["streets"][int(nid)])
    f = plot.get("f")
    if f:
        return street_at(town, int(f[1]) * int(town["side"]) + int(f[0]))
    return ""


def _district(cell: dict[str, Any], d: Any) -> dict[str, Any]:
    districts = [x for x in cell.get("districts") or [] if isinstance(x, dict)]
    try:
        k = int(d)
    except (TypeError, ValueError):
        return {}
    return districts[k] if 0 <= k < len(districts) else {}


def ward_at(town: dict[str, Any], cell: dict[str, Any], i: int) -> dict[str, Any]:
    """The ward a road tile runs through: the district of the nearest plot facing it."""
    side = int(town["side"])
    front = _ix(town)["front"]
    x, y = i % side, i // side
    for r in range(0, 7):
        for yy in range(max(0, y - r), min(side, y + r + 1)):
            for xx in range(max(0, x - r), min(side, x + r + 1)):
                if max(abs(xx - x), abs(yy - y)) != r:
                    continue
                for plot in front.get(yy * side + xx) or []:
                    found = _district(cell, plot.get("d"))
                    if found:
                        return found
    best, best_d = {}, None
    for district in cell.get("districts") or []:
        if not isinstance(district, dict) or district.get("type") == "street":
            continue
        anchor = district.get("anchor") or [0, 0]
        dist = abs(int(anchor[0]) - x) + abs(int(anchor[1]) - y)
        if best_d is None or dist < best_d:
            best, best_d = district, dist
    return best


def plot_label(plot: dict[str, Any]) -> str:
    return tg._plot_label(plot)


def compass(dx: int, dy: int) -> str:
    from app.local_intel import compass_word

    return compass_word(int(dx), int(dy)) or "here"


# ---------------------------------------------------------------------------
# Roads: paths and distances
# ---------------------------------------------------------------------------


def _bfs_path(town: dict[str, Any], start: int, goals: set[int]) -> list[int] | None:
    """Shortest road path from ``start`` to the first goal tile (4-neighbour)."""
    side = int(town["side"])
    roads = town["roads"]
    if start in goals:
        return [start]
    prev = [-1] * (side * side)
    prev[start] = start
    queue = deque([start])
    while queue:
        i = queue.popleft()
        x, y = i % side, i // side
        for dx, dy in _N4:
            nx, ny = x + dx, y + dy
            if 0 <= nx < side and 0 <= ny < side:
                j = ny * side + nx
                if roads[j] and prev[j] < 0:
                    prev[j] = i
                    if j in goals:
                        path = [j]
                        while path[-1] != start:
                            path.append(prev[path[-1]])
                        path.reverse()
                        return path
                    queue.append(j)
    return None


def _road_dist(town: dict[str, Any], start: int, limit: int | None = None) -> dict[int, int]:
    side = int(town["side"])
    roads = town["roads"]
    dist = {start: 0}
    queue = deque([start])
    while queue:
        i = queue.popleft()
        d = dist[i]
        if limit is not None and d >= limit:
            continue
        x, y = i % side, i // side
        for dx, dy in _N4:
            nx, ny = x + dx, y + dy
            if 0 <= nx < side and 0 <= ny < side:
                j = ny * side + nx
                if roads[j] and j not in dist:
                    dist[j] = d + 1
                    queue.append(j)
    return dist


def nearest_road(town: dict[str, Any], x: int, y: int) -> int | None:
    side = int(town["side"])
    found = tg._nearest_road_tile(town["roads"], side, int(x), int(y))
    if found is None:
        return None
    return int(found[1]) * side + int(found[0])


def _cell_route(city: dict[str, Any], a: tuple[int, int], b: tuple[int, int]) -> list[tuple[int, int]] | None:
    cells = set(tg._city_cells(city))
    if a not in cells or b not in cells:
        return None
    prev = {a: a}
    queue = deque([a])
    while queue:
        cur = queue.popleft()
        if cur == b:
            route = [cur]
            while route[-1] != a:
                route.append(prev[route[-1]])
            route.reverse()
            return route
        for dx, dy in _N4:
            nxt = (cur[0] + dx, cur[1] + dy)
            if nxt in cells and nxt not in prev:
                prev[nxt] = cur
                queue.append(nxt)
    return None


def _shared_ports(chart: dict[str, Any], city: dict[str, Any], a: tuple[int, int], b: tuple[int, int]) -> list[tuple[dict, dict]]:
    ports = tg.city_ports(chart, city)
    pa = [p for p in ports.get(a, []) if p.get("to") and (int(p["to"][0]), int(p["to"][1])) == b]
    pb = [p for p in ports.get(b, []) if p.get("to") and (int(p["to"][0]), int(p["to"][1])) == a]
    pairs = []
    for p in pa:
        q = next((q for q in pb if float(q["t"]) == float(p["t"]) and q.get("cls") == p.get("cls")), None)
        if q is None and pb:
            q = pb[0]
        if q is not None:
            pairs.append((p, q))
    return pairs


def _port_index(port: dict[str, Any], side: int) -> int:
    x, y = tg.port_tile(port, side)
    return int(y) * int(side) + int(x)


def _crossings(town_a: dict[str, Any], town_b: dict[str, Any], edge_a: str) -> list[tuple[int, int]]:
    """Road tiles that meet across a shared edge: (tile in a, tile in b) (playtest #70).

    Tile k of a side-s edge covers metres [k, k+1) * 800 / s. Two road tiles
    whose spans overlap are one crossing, whatever generated them: ports,
    avenues that happen to line up, v2 joins, or a v2 cell meeting the dead
    ends of a stored v1 neighbour. Before this only the ports crossed.
    """
    sa, sb = int(town_a["side"]), int(town_b["side"])
    ra, rb = town_a["roads"], town_b["roads"]
    row_a = tg.edge_tiles(sa, edge_a)
    row_b = tg.edge_tiles(sb, tg._OPPOSITE[edge_a])
    pairs: list[tuple[int, int]] = []
    for k, i in enumerate(row_a):
        if not ra[i]:
            continue
        k0 = (k * sb) // sa
        k1 = min(sb - 1, -(-((k + 1) * sb) // sa) - 1)
        mid = (k + 0.5) * sb / sa - 0.5
        hits = [kb for kb in range(k0, max(k0, k1) + 1) if rb[row_b[kb]]]
        if hits:
            kb = min(hits, key=lambda h: (abs(h - mid), h))
            pairs.append((i, row_b[kb]))
    return pairs


class _CellSource:
    """Cells a turn may read or generate, with the per-turn generation cap (TownGrid.md 3.6)."""

    def __init__(self, conn, chart: dict[str, Any], *, generate: bool, cap: int = MAX_CELLS_PER_TURN):
        self.conn = conn
        self.chart = chart
        self.generate = generate
        self.left = int(cap)
        self.made: list[tuple[int, int]] = []

    def get(self, cx: int, cy: int) -> dict[str, Any] | None:
        town = tg.stored_cell(self.conn, self.chart, cx, cy)
        if town is not None or not self.generate or self.left <= 0:
            return town
        town = tg.get_cell(self.conn, self.chart, cx, cy, create=True)
        if town is not None:
            self.left -= 1
            self.made.append((int(cx), int(cy)))
        return town


def _walk(source: _CellSource, city: dict[str, Any], start: tuple[int, int, int], dest: tuple[int, int],
          goals: set[int], *, budget: float) -> dict[str, Any]:
    """Walk the roads from ``start`` (cx, cy, tile) to any goal tile in cell ``dest``.

    Fine BFS inside each cell, crossing cells wherever roads meet across the
    shared edge (_crossings; the ports when the next cell cannot be read).
    Stops where the minutes run out (``partial``). Cells are generated only as
    the walk reaches them.
    """
    route = _cell_route(city, (start[0], start[1]), dest)
    if not route:
        return {"ok": False, "reason": "no_route"}
    legs: list[dict[str, Any]] = []
    cur = int(start[2])
    minutes = 0.0
    partial = False
    remaining = 0.0
    cells = tg._city_cells(city)
    for k, (cx, cy) in enumerate(route):
        town = source.get(cx, cy)
        if town is None:
            partial = True
            remaining += sum(tg.cell_cross_minutes() for _ in route[k:])
            break
        side = int(town["side"])
        tmin = tg.tile_minutes(side)
        last = k == len(route) - 1
        if last:
            targets: dict[int, Any] = {g: None for g in goals}
        else:
            targets = {}
            nxt = route[k + 1]
            # Read, never generate, the next cell here: it is generated only
            # when the walk reaches it, and until then the ports cross.
            ntown = tg.stored_cell(source.conn, source.chart, nxt[0], nxt[1])
            if ntown is not None:
                edge = _STEP_EDGE.get((nxt[0] - cx, nxt[1] - cy), "")
                for ia, ib in _crossings(town, ntown, edge) if edge else []:
                    targets.setdefault(ia, ib)
            if not targets:
                nside = tg._side(cells[nxt])
                for p, q in _shared_ports(source.chart, city, (cx, cy), nxt):
                    targets.setdefault(_port_index(p, side), _port_index(q, nside))
        path = _bfs_path(town, cur, set(targets))
        if path is None:
            return {"ok": False, "reason": "no_road", "legs": legs}
        cost = (len(path) - 1) * tmin + (tmin if k > 0 else 0.0)
        if minutes + cost > budget + 1e-9:
            can = max(0, int(math.floor((budget - minutes - (tmin if k > 0 else 0.0)) / tmin)))
            if k > 0 and budget - minutes < tmin:
                partial = True
                remaining += cost + sum(tg.cell_cross_minutes() for _ in route[k + 1:])
                break
            cut = path[: can + 1]
            remaining += (len(path) - len(cut)) * tmin + sum(tg.cell_cross_minutes() for _ in route[k + 1:])
            minutes += (len(cut) - 1) * tmin + (tmin if k > 0 else 0.0)
            legs.append({"cx": cx, "cy": cy, "side": side, "tiles": cut})
            partial = True
            break
        minutes += cost
        legs.append({"cx": cx, "cy": cy, "side": side, "tiles": path})
        if not last:
            cur = int(targets[path[-1]])
    if not legs:
        return {"ok": False, "reason": "ungenerated", "partial": True}
    end_leg = legs[-1]
    end = (int(end_leg["cx"]), int(end_leg["cy"]), int(end_leg["tiles"][-1]))
    steps = sum(len(leg["tiles"]) - 1 for leg in legs) + (len(legs) - 1)
    heading = ""
    tiles = end_leg["tiles"]
    if len(tiles) >= 2:
        side = int(end_leg["side"])
        a, b = tiles[-2], tiles[-1]
        heading = {(0, -1): "N", (1, 0): "E", (0, 1): "S", (-1, 0): "W"}.get(
            ((b % side) - (a % side), (b // side) - (a // side)), ""
        )
    elif len(legs) >= 2:
        prev_leg = legs[-2]
        heading = {(0, -1): "N", (1, 0): "E", (0, 1): "S", (-1, 0): "W"}.get(
            (int(end_leg["cx"]) - int(prev_leg["cx"]), int(end_leg["cy"]) - int(prev_leg["cy"])), ""
        )
    return {
        "ok": True,
        "legs": legs,
        "steps": steps,
        "minutes": (max(1, int(math.ceil(minutes - 1e-9))) if steps else 0),
        "partial": partial,
        "remaining_minutes": int(math.ceil(remaining)) if partial else 0,
        "end": end,
        "heading": heading,
        "reached": (not partial) and end[0:2] == tuple(dest) and end[2] in goals,
    }


# ---------------------------------------------------------------------------
# Knowledge: what the player has seen, read, been told
# ---------------------------------------------------------------------------


def _sight(town: dict[str, Any], tiles: list[int], heading: str = "") -> tuple[set[int], set[int]]:
    """Road tiles in sight of a walk, and plots whose sign can be read from it (TownGrid.md 6)."""
    side = int(town["side"])
    tm = tg.tile_metres(side)
    r = max(3, int(round(SIGHT_METRES / tm)))
    rd = max(1, int(round(READ_METRES / tm)))
    roads = town["roads"]
    front = _ix(town)["front"]
    seen: set[int] = set()
    read: set[int] = set()
    if not tiles:
        return seen, read
    stride = max(1, r // 2)
    sample = list(dict.fromkeys(list(tiles[::stride]) + [tiles[-1]]))
    for i in sample:
        x, y = i % side, i // side
        for yy in range(max(0, y - r), min(side, y + r + 1)):
            row = yy * side
            for xx in range(max(0, x - r), min(side, x + r + 1)):
                if roads[row + xx]:
                    seen.add(row + xx)
    for i in dict.fromkeys(tiles):
        x, y = i % side, i // side
        for yy in range(max(0, y - rd), min(side, y + rd + 1)):
            for xx in range(max(0, x - rd), min(side, x + rd + 1)):
                for plot in front.get(yy * side + xx) or ():
                    read.add(int(plot["n"]))
    step = _HEADING_STEP.get(str(heading or ""))
    if step:
        x, y = tiles[-1] % side, tiles[-1] // side
        for _ in range(max(1, int(round(AHEAD_METRES / tm)))):
            x, y = x + step[0], y + step[1]
            if not (0 <= x < side and 0 <= y < side) or not roads[y * side + x]:
                break
            seen.add(y * side + x)
    return seen, read


def _claimed_plots(conn, city_id: str) -> dict[str, int]:
    try:
        rows = conn.execute(
            "SELECT id, workplace_plot FROM npcs WHERE COALESCE(workplace_plot, '') LIKE ?", (f"{city_id}.%",)
        ).fetchall()
    except Exception:
        return {}
    return {str(r["workplace_plot"]): int(r["id"]) for r in rows}


class _Knowledge:
    """What the player knows of one generated cell, plus what this turn's walk will add."""

    def __init__(self, conn, chart: dict[str, Any], town: dict[str, Any], *, realized: Iterable[str] = (),
                 claimed: Iterable[str] = (), extra_roads: Iterable[int] = (), extra_read: Iterable[int] = ()):
        side = int(town["side"])
        fold = tg.fold_seen(conn, str(chart.get("id") or ""), int(town["cx"]), int(town["cy"]), side, len(town["plots"]))
        self.side = side
        self.bits = fold["roads"]
        self.extra_roads = set(int(i) for i in extra_roads)
        read = {n for n in range(len(town["plots"])) if (n >> 3) < len(fold["plots"]) and tg._bit(fold["plots"], n)}
        read |= tg._told_plot_ns(town, fold["told"])
        ids = {str(p["id"]): int(p["n"]) for p in town["plots"]}
        for pid in list(realized) + list(claimed):
            if pid in ids:
                read.add(ids[pid])
        read |= set(int(n) for n in extra_read)
        self.read = read

    def road_seen(self, i: int) -> bool:
        return i in self.extra_roads or tg._bit(self.bits, int(i))

    def kind_known(self, plot: dict[str, Any]) -> bool:
        if int(plot["n"]) in self.read or plot.get("k") == "gate":
            return True
        f = plot.get("f")
        return bool(f) and self.road_seen(int(f[1]) * self.side + int(f[0]))

    def name_known(self, plot: dict[str, Any]) -> bool:
        return bool(plot.get("name")) and (int(plot["n"]) in self.read or plot.get("k") == "gate")


def _generated_cells(conn, chart: dict[str, Any], city_id: str) -> list[tuple[int, int]]:
    try:
        rows = conn.execute(
            "SELECT cx, cy FROM town_cells WHERE map_id = ? AND city_id = ? ORDER BY cx, cy",
            (str(chart.get("id") or ""), str(city_id)),
        ).fetchall()
    except Exception:
        return []
    return [(int(r["cx"]), int(r["cy"])) for r in rows]


def _realized_rows(conn, city_id: str) -> dict[str, dict[str, Any]]:
    try:
        rows = conn.execute(
            "SELECT id, code, name, plot_id, keeper_npc_id FROM locations WHERE COALESCE(plot_id, '') LIKE ?",
            (f"{city_id}.%",),
        ).fetchall()
    except Exception:
        return {}
    return {str(r["plot_id"]): dict(r) for r in rows}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9' ]+", " ", venues._fold(text))).strip()


def _bare(name: str) -> str:
    return re.sub(r"^the\s+", "", _norm(name))


def _named_in(text_norm: str, name: str) -> int:
    """Length of ``name`` when the normalized text names it (with or without its "The"), else 0."""
    for form in dict.fromkeys((_norm(name), _bare(name))):
        if len(form) >= 4 and re.search(rf"(?<![a-z0-9]){re.escape(form)}(?![a-z0-9])", text_norm):
            return len(form)
    return 0


# ---------------------------------------------------------------------------
# Settlement rows and plot realization (TownGrid.md 4.2, 4.4)
# ---------------------------------------------------------------------------


def settlement_row(conn, city: dict[str, Any], *, create: bool = True) -> int:
    """The city's settlement location row: found, adopted by name, or made. 0 when absent and not made."""
    from app import world as W

    city_id = str(city.get("id") or "")
    name = str(city.get("name") or "").strip() or city_id
    size = tg.settlement_size_for_band(str(city.get("band") or ""))
    row = conn.execute(
        "SELECT id FROM locations WHERE city_id = ? AND COALESCE(plot_id, '') = '' AND COALESCE(kind, '') = '' "
        "AND COALESCE(parent_id, 0) = 0 ORDER BY id LIMIT 1",
        (city_id,),
    ).fetchone()
    if row is not None:
        return int(row["id"])
    adopt = conn.execute(
        "SELECT id FROM locations WHERE COALESCE(parent_id, 0) = 0 AND COALESCE(kind, '') = '' "
        "AND COALESCE(city_id, '') = '' AND name = ? COLLATE NOCASE ORDER BY id LIMIT 1",
        (name,),
    ).fetchone()
    if not create:
        return int(adopt["id"]) if adopt is not None else 0
    if adopt is not None:
        conn.execute(
            "UPDATE locations SET city_id = ?, settlement_size = ? WHERE id = ?", (city_id, size, int(adopt["id"]))
        )
        return int(adopt["id"])
    stored = name
    if conn.execute("SELECT 1 FROM locations WHERE name = ? COLLATE NOCASE", (stored,)).fetchone():
        # A venue already holds the name: the band word is a place-tail word, so
        # the settlement row never classifies as a shop.
        stored = f"{name} {'city' if size == 'city' else 'town'}"
        n = 2
        while conn.execute("SELECT 1 FROM locations WHERE name = ? COLLATE NOCASE", (stored,)).fetchone():
            stored = f"{name} {'city' if size == 'city' else 'town'} {n}"
            n += 1
    label = {"city": "city", "town": "town", "village": "village", "hamlet": "hamlet"}.get(size, "settlement")
    cursor = conn.execute(
        "INSERT INTO locations (code, name, summary, visit_count, settlement_size, city_id) VALUES (?, ?, ?, 0, ?, ?)",
        (W._next_code(conn, "locations", "L"), stored, f"The {label} of {name}."[:400], size, city_id),
    )
    return int(cursor.lastrowid)


def snapshot_town_rows(conn, town_turn: dict[str, Any] | None, rows: dict[str, list[dict[str, Any]]]) -> None:
    """Add to the rewind record the rows apply_town_turn changes in place (TownGrid.md 9).

    apply_town_turn runs after the snapshot. Rows it inserts sit above the
    snapshot's max ids, but two writes change existing rows: realize_plot sets
    workplace_id and clears workplace_plan on the plot's claimants, and
    settlement_row adopts a same-named row by stamping city_id. Those rows go
    into the record here, before the turn writes them.
    """
    from app import world as W

    if not town_turn:
        return
    chart = world_chart(conn)
    if chart is None:
        return
    pos = town_turn.get("position") or {}
    city = city_by_id(chart, str(pos.get("city_id") or ""))
    if city is not None:
        city_id = str(city.get("id") or "")
        own = conn.execute(
            "SELECT 1 FROM locations WHERE city_id = ? AND COALESCE(plot_id, '') = '' AND COALESCE(kind, '') = '' "
            "AND COALESCE(parent_id, 0) = 0 LIMIT 1",
            (city_id,),
        ).fetchone()
        if own is None:
            name = str(city.get("name") or "").strip() or city_id
            W._snapshot_row(
                conn, "locations",
                "COALESCE(parent_id, 0) = 0 AND COALESCE(kind, '') = '' AND COALESCE(city_id, '') = '' "
                "AND name = ? COLLATE NOCASE",
                (name,), rows,
            )
    plot_ref = str(((town_turn.get("plan") or {}).get("target") or {}).get("plot") or "")
    if plot_ref:
        W._snapshot_row(conn, "npcs", "workplace_plot = ?", (plot_ref,), rows)


def locate_plot(conn, chart: dict[str, Any], plot_ref: str) -> tuple[dict, dict, dict, dict] | None:
    """(city, cell meta, generated town, plot) for a plot id in a generated cell, else None."""
    parsed = tg.parse_plot_id(plot_ref)
    if parsed is None:
        return None
    city_id, lx, ly, n = parsed
    city = city_by_id(chart, city_id)
    if city is None:
        return None
    cell = next((c for c in tg._city_cells(city).values() if [int(v) for v in (c.get("local") or [0, 0])] == [lx, ly]), None)
    if cell is None:
        return None
    town = tg.stored_cell(conn, chart, int(cell["x"]), int(cell["y"]))
    if town is None or not (0 <= n < len(town["plots"])):
        return None
    return city, cell, town, town["plots"][n]


def realize_plot(conn, chart: dict[str, Any], plot_ref: str) -> int:
    """The plot's locations row, made now if it is not one yet; 0 when the plot is unknown.

    Idempotent. The row is a child of the city's settlement row, stamped with
    the plot's kind and hours. On a name clash with an unrelated row it is
    stored as "<name> on <street>" and the plain name becomes an alias.
    """
    from app import world as W

    existing = conn.execute("SELECT id FROM locations WHERE plot_id = ? ORDER BY id LIMIT 1", (str(plot_ref),)).fetchone()
    if existing is not None:
        return int(existing["id"])
    found = locate_plot(conn, chart, plot_ref)
    if found is None:
        return 0
    city, cell, town, plot = found
    parent_id = settlement_row(conn, city, create=True)
    vk = str(plot.get("vk") or "")
    street = _plot_street(town, plot)
    ward = _district(cell, plot.get("d"))
    label = plot_label(plot)
    name = str(plot.get("name") or "").strip()
    if not name:
        name = f"{street} {label.title()}".strip() if street else f"{str(ward.get('name') or city.get('name') or '')} {label.title()}".strip()
    stored = name
    clash = conn.execute("SELECT 1 FROM locations WHERE name = ? COLLATE NOCASE", (stored,)).fetchone() is not None
    if clash:
        stored = f"{name} on {street}" if street else f"{name} in {ward.get('name') or city.get('name')}"
        n = 2
        while conn.execute("SELECT 1 FROM locations WHERE name = ? COLLATE NOCASE", (stored,)).fetchone():
            stored = f"{name} on {street} {n}" if street else f"{name} {n}"
            n += 1
    summary = f"{label[:1].upper() + label[1:]} on {street or 'a lane'}, {ward.get('name') or city.get('name') or ''}".strip(", ")
    code = W._next_code(conn, "locations", "L")
    cursor = conn.execute(
        "INSERT INTO locations (code, name, summary, visit_count, plot_id, city_id) VALUES (?, ?, ?, 0, ?, ?)",
        (code, stored, summary[:400], str(plot_ref), str(city.get("id") or "")),
    )
    venue_id = int(cursor.lastrowid)
    W.stamp_venue_fields(conn, venue_id, parent_id=parent_id, kind=vk)
    if not vk:
        conn.execute("UPDATE locations SET kind = ? WHERE id = ?", (str(plot.get("k") or ""), venue_id))
    if clash:
        try:
            conn.execute(
                "INSERT OR IGNORE INTO aliases (alias, entity_type, entity_code) VALUES (?, 'location', ?)",
                (name, code),
            )
        except Exception:
            pass
    # Whoever already claimed this plot as their workplace keeps it.
    keeper = conn.execute(
        "SELECT id FROM npcs WHERE workplace_plot = ? AND COALESCE(shell, 0) = 0 ORDER BY id LIMIT 1", (str(plot_ref),)
    ).fetchone()
    if keeper is not None:
        conn.execute("UPDATE locations SET keeper_npc_id = ? WHERE id = ?", (int(keeper["id"]), venue_id))
        conn.execute(
            "UPDATE npcs SET workplace_id = ?, workplace_plan = '' WHERE workplace_plot = ?", (venue_id, str(plot_ref))
        )
    return venue_id


# ---------------------------------------------------------------------------
# Where the player comes in
# ---------------------------------------------------------------------------


def entry_tile(chart: dict[str, Any], city: dict[str, Any], cell: dict[str, Any], town: dict[str, Any],
               came_from: tuple[int, int] | None = None) -> int:
    """The road tile a player stands on after stepping into this cell (TownGrid.md 4.2)."""
    side = int(town["side"])
    cx, cy = int(cell["x"]), int(cell["y"])
    ports = tg.city_ports(chart, city).get((cx, cy), [])
    if came_from is not None and tuple(came_from) != (cx, cy):
        dx, dy = cx - int(came_from[0]), cy - int(came_from[1])
        sx = (dx > 0) - (dx < 0)
        sy = (dy > 0) - (dy < 0)
        edge = _EDGE_FROM_STEP.get((sx, 0) if sx else (0, sy), "")
        neighbour = (int(came_from[0]), int(came_from[1]))
        for port in ports:
            if port.get("to") and (int(port["to"][0]), int(port["to"][1])) == neighbour:
                return _port_index(port, side)
        compass_word = _EDGE_COMPASS.get(edge, "")
        for plot in town["plots"]:
            if plot.get("k") == "gate" and str(plot.get("gate") or "") == compass_word and plot.get("f"):
                return int(plot["f"][1]) * side + int(plot["f"][0])
        for port in ports:
            if port.get("gate") and port.get("edge") == edge:
                return _port_index(port, side)
        mid = side // 2
        target = {"N": (mid, 0), "S": (mid, side - 1), "W": (0, mid), "E": (side - 1, mid)}.get(edge, (mid, mid))
        found = nearest_road(town, *target)
        if found is not None:
            return found
    for district in cell.get("districts") or []:
        if isinstance(district, dict) and district.get("type") == "shopping":
            anchor = district.get("anchor") or [side // 2, side // 2]
            found = nearest_road(town, int(anchor[0]), int(anchor[1]))
            if found is not None:
                return found
    found = nearest_road(town, side // 2, side // 2)
    if found is not None:
        return found
    for i in range(side * side):
        if town["roads"][i]:
            return i
    return 0


def _set_marker(conn, chart: dict[str, Any], cx: int, cy: int) -> None:
    """Put the world-map marker on (cx, cy) with no travel cost, on this connection."""
    from app.tile_world import _save_map_payload, mark_visited

    if player_cell(chart) == (int(cx), int(cy)):
        return
    chart["player"] = {"x": int(cx), "y": int(cy)}
    try:
        mark_visited(chart, int(cx), int(cy))
    except Exception:
        pass
    _save_map_payload(chart, conn=conn)


def _record_walk_seen(conn, chart: dict[str, Any], legs: list[dict[str, Any]], heading: str, turn: int) -> None:
    for k, leg in enumerate(legs):
        town = tg.stored_cell(conn, chart, int(leg["cx"]), int(leg["cy"]))
        if town is None:
            continue
        roads, read = _sight(town, list(leg["tiles"]), heading if k == len(legs) - 1 else "")
        tg.record_seen(conn, str(chart.get("id") or ""), int(leg["cx"]), int(leg["cy"]), int(town["side"]),
                       road_tiles=sorted(roads), plot_ns=sorted(read), turn=turn)


def _current_location(conn) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT l.* FROM player p JOIN locations l ON l.id = p.current_location_id WHERE p.id = 1"
    ).fetchone()
    return dict(row) if row is not None else None


def enter_town(conn, chart: dict[str, Any], came_from: tuple[int, int] | None, *, move_location: bool = True,
               turn: int = 0) -> dict[str, Any] | None:
    """Stand the player on a road tile of the city cell the marker is on. Returns the position.

    ``came_from`` is the world cell they stepped from (None at a game start).
    Used by map steps and story walks; a turn's own placement goes through
    plan_turn / apply_town_turn instead.
    """
    cx, cy = player_cell(chart)
    located = tg._locate(chart, cx, cy)
    if located is None:
        return None
    city, cell = located
    town = tg.get_cell(conn, chart, cx, cy, create=True)
    if town is None:
        return None
    i = entry_tile(chart, city, cell, town, came_from)
    pos = _make_position(chart, city, cx, cy, town, i)
    write_position(conn, pos)
    roads, read = _sight(town, [i])
    tg.record_seen(conn, str(chart.get("id") or ""), cx, cy, int(town["side"]), road_tiles=sorted(roads),
                   plot_ns=sorted(read), turn=turn)
    settle = settlement_row(conn, city, create=True)
    if move_location and settle:
        here = _current_location(conn)
        stays = here is not None and (
            int(here.get("id") or 0) == settle
            or (str(here.get("city_id") or "") == str(city.get("id") or "") and not str(here.get("plot_id") or ""))
        )
        if not stays:
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (settle,))
    return pos


def sync_after_world_move(conn, chart: dict[str, Any] | None, came_from: tuple[int, int], *,
                          move_location: bool = True, turn: int = 0) -> dict[str, Any]:
    """Keep town_position and the world marker together after a world-map step (TownGrid.md 4.1).

    Out of every city: the position is cleared. Into a city cell (from outside,
    from another city, or from a neighbouring cell of the same city): the player
    stands at the gate, port or edge they came through.
    """
    if chart is None or str(chart.get("scale") or "") != "world":
        return {"status": "skipped"}
    here = player_cell(chart)
    pos = get_position(conn)
    if tuple(came_from) == here and pos and (int(pos.get("cx", -1)), int(pos.get("cy", -1))) == here:
        return {"status": "unchanged"}
    located = tg._locate(chart, *here)
    if located is None:
        if pos:
            clear_position(conn)
            return {"status": "left"}
        return {"status": "outside"}
    placed = enter_town(conn, chart, tuple(came_from), move_location=move_location, turn=turn)
    return {"status": "entered" if placed else "skipped", "position": placed}


def reconcile_marker(conn) -> bool:
    """After a rewind or a load: the world marker stands on town_position's cell (TownGrid.md 9)."""
    pos = get_position(conn)
    if not pos:
        return False
    chart = world_chart(conn)
    if chart is None or str(chart.get("id") or "") != str(pos.get("map_id") or ""):
        return False
    target = (int(pos.get("cx") or 0), int(pos.get("cy") or 0))
    if player_cell(chart) == target:
        return False
    _set_marker(conn, chart, *target)
    return True


# ---------------------------------------------------------------------------
# Typed targets (TownGrid.md 5.1)
# ---------------------------------------------------------------------------


def _leave_asked(words: str) -> re.Match | None:
    """A "leave town" the player means, not one they deny or complain about (playtest #71)."""
    for match in _LEAVE_RE.finditer(words or ""):
        window = words[max(0, match.start() - 48): match.start()]
        if _LEAVE_NOT_RE.search(window):
            continue
        return match
    return None


def _player_words(text: str) -> str:
    from app import world as W

    line = W._player_line(text)
    return venues.strip_speech(W._travel_scoring_text(line))


def _era(conn) -> str:
    try:
        from app import world as W

        return W._world_era(conn)
    except Exception:
        return ""


def _trade_words(era: str) -> list[tuple[str, str]]:
    """(word, kind) pairs a player uses for a trade, longest first, fitted to the era."""
    pairs: dict[str, str] = {}
    sources: list[tuple[str, Iterable[str]]] = []
    for kind, words in venues._KIND_WORDS.items():
        sources.append((kind, list(words) + [venues.kind_label(kind)]))
    for kind, words in venues._ROLE_KINDS.items():
        sources.append((kind, words))
    for kind, words in sources:
        fitted = venues.kind_for_era(kind, era) if era else kind
        if not fitted:
            continue
        for word in words:
            w = _norm(word)
            if len(w) >= 3 and w not in pairs:
                pairs[w] = fitted
    return sorted(pairs.items(), key=lambda item: -len(item[0]))


def _trade_asked(text_norm: str, era: str) -> tuple[str, str]:
    for word, kind in _trade_words(era):
        pattern = (
            rf"\b(?:the|a|an|nearest|closest|some|any|another|that|this|my|our|your|his|her|their)\s+"
            rf"(?:[a-z'-]+\s+){{0,2}}?{re.escape(word)}(?:s|es)?\b"
        )
        if re.search(pattern, text_norm):
            return word, kind
    return "", ""


def _plot_score(pos: dict[str, Any], cx: int, cy: int, plot: dict[str, Any], dist_here: dict[int, int], side_here: int) -> float:
    f = plot.get("f") or [0, 0]
    if (cx, cy) == (int(pos["cx"]), int(pos["cy"])):
        d = dist_here.get(int(f[1]) * side_here + int(f[0]))
        if d is not None:
            return float(d)
        return 1e6 + abs(int(f[0]) - int(pos["fx"])) + abs(int(f[1]) - int(pos["fy"]))
    cells = abs(cx - int(pos["cx"])) + abs(cy - int(pos["cy"]))
    return 1e4 * cells + abs(int(f[0]) - int(pos["fx"])) + abs(int(f[1]) - int(pos["fy"]))


class _CityView:
    """The generated cells of one city with the player's knowledge of each, for one plan."""

    def __init__(self, conn, chart: dict[str, Any], city: dict[str, Any], pos: dict[str, Any], source: _CellSource):
        self.conn = conn
        self.chart = chart
        self.city = city
        self.pos = pos
        self.source = source
        self.city_id = str(city.get("id") or "")
        self.cells = tg._city_cells(city)
        self.realized = _realized_rows(conn, self.city_id)
        self.claimed = _claimed_plots(conn, self.city_id)
        self._know: dict[tuple[int, int], _Knowledge] = {}
        self._dist_here: dict[int, int] | None = None

    def generated(self) -> list[tuple[int, int]]:
        return _generated_cells(self.conn, self.chart, self.city_id)

    def town(self, cx: int, cy: int) -> dict[str, Any] | None:
        return tg.stored_cell(self.conn, self.chart, cx, cy)

    def know(self, cx: int, cy: int) -> _Knowledge | None:
        key = (int(cx), int(cy))
        if key not in self._know:
            town = self.town(*key)
            if town is None:
                return None
            self._know[key] = _Knowledge(self.conn, self.chart, town, realized=self.realized, claimed=self.claimed)
        return self._know[key]

    def dist_here(self) -> dict[int, int]:
        if self._dist_here is None:
            town = self.town(int(self.pos["cx"]), int(self.pos["cy"]))
            self._dist_here = _road_dist(town, _pos_index(self.pos, int(town["side"]))) if town else {}
        return self._dist_here

    def side_here(self) -> int:
        return tg._side(self.cells[(int(self.pos["cx"]), int(self.pos["cy"]))])

    def plots(self, *, known: bool) -> Iterable[tuple[int, int, dict[str, Any]]]:
        for cx, cy in self.generated():
            town = self.town(cx, cy)
            if town is None:
                continue
            know = self.know(cx, cy) if known else None
            for plot in town["plots"]:
                if known and not know.name_known(plot):
                    continue
                yield cx, cy, plot

    def nearest(self, items: Iterable[tuple[int, int, dict[str, Any]]]) -> tuple[int, int, dict[str, Any]] | None:
        best, best_score = None, None
        dist, side = self.dist_here(), self.side_here()
        for cx, cy, plot in items:
            score = _plot_score(self.pos, cx, cy, plot, dist, side)
            if best_score is None or score < best_score:
                best, best_score = (cx, cy, plot), score
        return best


def _kind_matches(plot: dict[str, Any], kind: str) -> bool:
    return bool(kind) and str(plot.get("vk") or "") == kind and plot.get("k") in _DOOR_KINDS


def _lookup_cells(view: _CityView) -> list[tuple[int, int]]:
    """Ungenerated cells a lookup may generate: the whole of a small city, else the nearest 2."""
    have = set(view.generated())
    missing = [xy for xy in view.cells if xy not in have]
    px, py = int(view.pos["cx"]), int(view.pos["cy"])
    missing.sort(key=lambda xy: (abs(xy[0] - px) + abs(xy[1] - py), xy[1], xy[0]))
    if len(view.cells) <= SMALL_CITY_CELLS:
        return missing
    return missing[: tg.TOWN_LOOKUP_CELLS]


def find_kind(view: _CityView, kind: str, *, lookup: bool) -> tuple[str, tuple[int, int, dict[str, Any]] | None]:
    """("known" | "generated" | "lookup" | "none" | "unknown", the nearest plot of a trade)."""
    near_known = view.nearest((c for c in view.plots(known=True) if _kind_matches(c[2], kind)))
    if near_known is not None:
        return "known", near_known
    near_any = view.nearest((c for c in view.plots(known=False) if _kind_matches(c[2], kind)))
    if near_any is not None:
        return "generated", near_any
    if lookup:
        for cx, cy in _lookup_cells(view):
            view.source.get(cx, cy)
        near_any = view.nearest((c for c in view.plots(known=False) if _kind_matches(c[2], kind)))
        if near_any is not None:
            return "lookup", near_any
    if len(view.generated()) >= len(view.cells):
        return "none", None
    return "unknown", None


def _plot_named(view: _CityView, text_norm: str, *, known: bool = True) -> tuple[int, int, dict[str, Any]] | None:
    best, best_len = None, 0
    for cx, cy, plot in view.plots(known=known):
        if not plot.get("name"):
            continue
        n = _named_in(text_norm, str(plot["name"]))
        if n > best_len:
            best, best_len = (cx, cy, plot), n
    for pid, row in view.realized.items():
        n = _named_in(text_norm, str(row.get("name") or ""))
        if n > best_len:
            found = locate_plot(view.conn, view.chart, pid)
            if found is not None:
                best, best_len = (int(found[1]["x"]), int(found[1]["y"]), found[3]), n
    return best


def _street_named(view: _CityView, text_norm: str) -> tuple[int, int, set[int], str] | None:
    """(cx, cy, tiles of that street in its nearest cell, name) for a known street the text names."""
    best = None
    best_len = 0
    for cx, cy in view.generated():
        town = view.town(cx, cy)
        know = view.know(cx, cy)
        if town is None or know is None:
            continue
        side = int(town["side"])
        for seg in town["segments"]:
            nid = seg.get("name_id")
            if nid is None:
                continue
            name = str(town["streets"][int(nid)])
            n = _named_in(text_norm, name)
            if not n or n < best_len:
                continue
            tiles = set(tg._segment_tiles(seg, side))
            if not any(know.road_seen(i) for i in tiles) and seg.get("cls") not in (tg.ROAD_AVENUE, tg.ROAD_MAIN):
                continue
            score = abs(cx - int(view.pos["cx"])) + abs(cy - int(view.pos["cy"]))
            if best is None or n > best_len or (n == best_len and score < best[4]):
                best = (cx, cy, tiles, name, score)
                best_len = n
            elif best is not None and n == best_len and (cx, cy) == best[0:2]:
                best = (cx, cy, best[2] | tiles, name, score)
    return best[0:4] if best else None


def _ward_named(view: _CityView, text_norm: str) -> tuple[int, int, dict[str, Any]] | None:
    from app.town_grid import _seen_world_cells

    seen = _seen_world_cells(view.chart)
    best, best_len = None, 0
    for (cx, cy), cell in view.cells.items():
        if f"{cx},{cy}" not in seen:
            continue
        for district in cell.get("districts") or []:
            if not isinstance(district, dict) or district.get("type") == "street" or not district.get("name"):
                continue
            n = _named_in(text_norm, str(district["name"]))
            if n > best_len:
                best, best_len = (cx, cy, district), n
    if best is None:
        for word, ward_type in _WARD_WORDS.items():
            if re.search(rf"\bthe\s+{word}\b", text_norm):
                px, py = int(view.pos["cx"]), int(view.pos["cy"])
                options = []
                for (cx, cy), cell in view.cells.items():
                    if f"{cx},{cy}" not in seen:
                        continue
                    for district in cell.get("districts") or []:
                        if isinstance(district, dict) and district.get("type") == ward_type:
                            options.append((abs(cx - px) + abs(cy - py), cx, cy, district))
                if options:
                    options.sort(key=lambda o: o[:3])
                    best = (options[0][1], options[0][2], options[0][3])
                break
    return best


def _gate_target(view: _CityView, compass_word: str) -> tuple[int, int, int, dict[str, Any]] | None:
    ports = tg.city_ports(view.chart, view.city)
    px, py = int(view.pos["cx"]), int(view.pos["cy"])
    options = []
    for (cx, cy), items in ports.items():
        for port in items:
            if not port.get("gate"):
                continue
            if compass_word and str(port.get("gate")) != compass_word:
                continue
            side = tg._side(view.cells[(cx, cy)])
            options.append((abs(cx - px) + abs(cy - py), cx, cy, float(port["t"]), port, side))
    if not options:
        return None
    options.sort(key=lambda o: o[:4])
    _, cx, cy, _t, port, side = options[0]
    return cx, cy, _port_index(port, side), port


def _target_entry(cx: int, cy: int, plot: dict[str, Any], town_side: int) -> dict[str, Any]:
    return {
        "plot": str(plot["id"]),
        "name": str(plot.get("name") or ""),
        "label": plot_label(plot),
        "k": str(plot.get("k") or ""),
        "vk": str(plot.get("vk") or ""),
        "cx": cx,
        "cy": cy,
    }


def _world_minute(conn) -> int:
    try:
        from app import world as W

        return int(W._world_minute(conn))
    except Exception:
        return 0


def _open_at(plot: dict[str, Any], minute: int) -> bool:
    vk = str(plot.get("vk") or "")
    if not vk:
        return True
    hours = venues.default_hours(vk)
    return bool(venues.is_open(hours[0], hours[1], int(minute)))


def _hours(plot: dict[str, Any]) -> str:
    vk = str(plot.get("vk") or "")
    if not vk:
        return ""
    return venues.describe_hours(*venues.default_hours(vk))


def _preview(conn, minutes: int, context: dict[str, Any] | None) -> dict[str, Any]:
    """Would a town walk of ``minutes`` be blocked? Pure (TownGrid.md 4.3)."""
    if int(minutes) <= 0:
        return {"blocked": False, "reasons": []}
    try:
        from app import world as W
        from app.player_resources import preview_travel_spend

        context = context or {}
        opts = ((context.get("settings") or {}).get("playthrough_options") or {}) if isinstance(context.get("settings"), dict) else {}
        if not isinstance(opts, dict) or not opts:
            opts = W._settings(conn).get("playthrough_options") or {}
        if not isinstance(opts, dict):
            opts = {}
        inv_sum = context.get("inventory_summary") or {}
        cap = max(1.0, float(inv_sum.get("weight_capacity") or 60.0))
        eff = max(0.0, float(inv_sum.get("effective_weight") or 0.0))
        load_ratio = min(2.2, eff / cap) if cap else 0.4
        wx = W.get_weather(conn)
        wmult = float(W.WEATHER_TRAVEL_MULT.get(str((wx or {}).get("kind") or "clear"), 1.0))
        strength = max(0.0, min(1.0, float(W._float((wx or {}).get("strength"), 0.0))))
        if wmult > 1.0:
            wmult = 1.0 + (wmult - 1.0) * (0.5 + 0.5 * strength)
        player = context.get("player") if isinstance(context.get("player"), dict) else {}
        stats = W._gear_scores(player.get("effective_stats")) if isinstance(player.get("effective_stats"), dict) else None
        found = preview_travel_spend(
            conn, terrain="city", minutes=int(minutes), load_ratio=load_ratio, weather_mult=wmult,
            options=opts, stats=stats, hard_block=True,
        )
        return {"blocked": bool(found.get("blocked")), "reasons": list(found.get("reasons") or [])}
    except Exception:
        return {"blocked": False, "reasons": []}


def _plan_walk(view: _CityView, dest: tuple[int, int], goals: set[int], *, kind: str, rule: str,
               target: dict[str, Any], enter: bool, context: dict[str, Any] | None,
               budget: float | None = None) -> dict[str, Any]:
    pos = view.pos
    side = view.side_here()
    start = (int(pos["cx"]), int(pos["cy"]), _pos_index(pos, side))
    walk = _walk(view.source, view.city, start, dest, goals,
                 budget=float(tg.town_walk_budget() if budget is None else budget))
    plan: dict[str, Any] = {
        "kind": kind,
        "rule": rule,
        "map_id": str(view.chart.get("id") or ""),
        "city_id": view.city_id,
        "from": {k: pos.get(k) for k in ("cx", "cy", "fx", "fy", "plot", "inside")},
        "target": target,
        "enter_wanted": bool(enter),
    }
    if not walk.get("ok"):
        plan.update({"kind": "stay", "rule": "town_unreachable", "reason": walk.get("reason") or "", "minutes": 0,
                     "legs": [], "partial": False, "blocked": False, "enter": False})
        return plan
    plan.update({k: walk[k] for k in ("legs", "steps", "minutes", "partial", "remaining_minutes", "end", "heading", "reached")})
    minute = _world_minute(view.conn) + int(walk["minutes"])
    plot = None
    if target.get("plot"):
        found = locate_plot(view.conn, view.chart, str(target["plot"]))
        plot = found[3] if found else None
    plan["open"] = _open_at(plot, minute) if plot is not None else True
    plan["enter"] = bool(enter and walk["reached"] and plan["open"] and plot is not None and plot.get("k") in _DOOR_KINDS)
    preview = _preview(view.conn, int(walk["minutes"]), context)
    plan["blocked"] = bool(preview["blocked"])
    plan["reasons"] = preview["reasons"]
    if plan["blocked"]:
        plan["enter"] = False
    return plan


# ---------------------------------------------------------------------------
# Out of town (playtest #71): one exit planner for a typed leave, the Leave
# control and a world-map pick made from inside a town
# ---------------------------------------------------------------------------

EXIT_CANDIDATES = 6


def across_town_budget(city: dict[str, Any]) -> float:
    """Minutes a walk across this whole town may take: a world-map pick from
    inside a town is one walk through the streets, not a turn's stroll."""
    return float(tg.town_walk_budget() + 2 * len(tg._city_cells(city)) * tg.cell_cross_minutes())


def _exit_walk(view: _CityView, target: tuple[int, int] | None, *, edge: str = "",
               context: dict[str, Any] | None, budget: float | None = None) -> dict[str, Any] | None:
    """A "leave" plan through the streets to the best way out, or None when none is reachable.

    Best: the outer edge whose world cell outside lies nearest ``target``,
    then the fewest cells to cross, then the shortest walk. ``edge`` keeps
    only exits on that side (a named gate, the Leave control). In an open
    town any road that reaches an outer edge is a way out; in a walled one
    only the gates are (tg.cell_exits).
    """
    walls = tg.town_walls(view.chart, view.city, _era(view.conn))
    here = (int(view.pos["cx"]), int(view.pos["cy"]))
    cands = []
    for (cx, cy) in view.cells:
        for e in tg.outer_edges(view.city, cx, cy):
            if edge and e != edge:
                continue
            dx, dy = _HEADING_STEP[e]
            out = (cx + dx, cy + dy)
            far = max(abs(out[0] - target[0]), abs(out[1] - target[1])) if target else 0
            route = _cell_route(view.city, here, (cx, cy)) or []
            cands.append((far, len(route), (cx, cy) != here, cy, cx, e, out))
    cands.sort()
    best = None
    tried = 0
    for far, hops, _away, cy, cx, e, out in cands:
        if best is not None and (far, hops) > best[0]:
            break
        if tried >= EXIT_CANDIDATES:
            break
        tried += 1
        town = view.source.get(cx, cy)
        if town is None:
            continue
        side = int(town["side"])
        exits = [ex for ex in tg.cell_exits(view.chart, view.city, view.cells[(cx, cy)], town["roads"], walls)
                 if ex["edge"] == e]
        if not exits:
            continue
        goals = {int(ex["y"]) * side + int(ex["x"]) for ex in exits}
        compass = _EDGE_COMPASS[e]
        plan = _plan_walk(view, (cx, cy), goals, kind="leave", rule="town_leave",
                          target={"name": f"the {compass} edge of town", "cx": cx, "cy": cy, "edge": e,
                                  "out": [out[0], out[1]]},
                          enter=False, context=context, budget=budget)
        if not plan.get("legs") or not plan.get("reached"):
            continue
        end = int(plan["end"][2])
        ex = next((x for x in exits if int(x["y"]) * side + int(x["x"]) == end), exits[0])
        if ex.get("kind") == "gate":
            label = str(ex.get("label") or f"{compass.title()} Gate")
            plan["target"].update({"name": f"the {label}" if not label.lower().startswith("the ") else label,
                                   "gate": str(ex.get("gate") or compass), "label": label})
            if walls.get("manned"):
                plan["target"]["checkpoint"] = True
        plan["walls"] = walls
        plan["exit"] = {"cx": cx, "cy": cy, "x": int(ex["x"]), "y": int(ex["y"]), "edge": e, "kind": ex.get("kind"),
                        "out": [out[0], out[1]]}
        key = ((far, hops), int(plan.get("minutes") or 0))
        if best is None or key < (best[0], best[1]):
            best = ((far, hops), int(plan.get("minutes") or 0), plan)
    return best[2] if best else None


def _gate_stop(conn, plan: dict[str, Any], pos: dict[str, Any]) -> str:
    """Why a walk out must stop at its gate first, or "" (playtest #71).

    Only a walled town's gate stops anyone: a manned checkpoint, or a gate
    shut for the night. A player already standing at that gate was stopped
    there before, so this time they go through: the stop is where the scene
    with the guard happens, never a wall the player cannot pass.
    """
    ex = plan.get("exit") or {}
    walls = plan.get("walls") or {}
    if ex.get("kind") != "gate" or not walls.get("walled"):
        return ""
    if (int(pos.get("cx", -1)), int(pos.get("cy", -1)), int(pos.get("fx", -1)), int(pos.get("fy", -1))) == (
        int(ex["cx"]), int(ex["cy"]), int(ex["x"]), int(ex["y"])
    ):
        return ""
    label = str((plan.get("target") or {}).get("label") or "The gate")
    if walls.get("manned"):
        return f"{label} is a checkpoint; the guards stop whoever passes. Speak with them, or leave again to go through."
    minute = (_world_minute(conn) + int(plan.get("minutes") or 0)) % (24 * 60)
    if not venues.is_open(tg.GATE_HOURS[0], tg.GATE_HOURS[1], minute):
        return (f"{label} is shut for the night (it opens at {venues.clock(tg.GATE_HOURS[0])}). "
                "Rouse the gatekeeper, or leave again to try the postern.")
    return ""


def plan_exit(conn, target: tuple[int, int] | None = None, *, edge: str = "",
              context: dict[str, Any] | None = None) -> dict[str, Any]:
    """The walk out of town toward ``target`` (a world cell), planned but not written.

    Raises ValueError when the player is not in a town or no way out is
    reachable. May generate the cells the walk crosses (town_cells cache rows).
    """
    chart = world_chart(conn)
    pos = get_position(conn)
    if chart is None or not pos:
        raise ValueError("You are not in a town.")
    city = city_by_id(chart, str(pos.get("city_id") or ""))
    if city is None:
        raise ValueError("You are not in a town.")
    view = _CityView(conn, chart, city, pos, _CellSource(conn, chart, generate=True))
    plan = _exit_walk(view, target, edge=edge, context=context, budget=across_town_budget(city))
    if plan is None and edge:
        plan = _exit_walk(view, target, context=context, budget=across_town_budget(city))
    if plan is None:
        raise ValueError("No road you know leads out of town from here.")
    plan["halt"] = _gate_stop(conn, plan, pos)
    return plan


def _commit_walk(conn, plan: dict[str, Any], pos: dict[str, Any], context: dict[str, Any] | None) -> dict[str, Any]:
    """Preview, commit, advance one engine walk outside a turn (click-walk, Leave, map pick)."""
    result: dict[str, Any] = {"player": {}}
    report = apply_town_turn(conn, {"position": pos, "plan": plan, "placed": None}, result, context,
                             turn=_turn(conn)) or {}
    code = (result.get("player") or {}).get("move_to_location_code")
    if code:
        row = conn.execute("SELECT id FROM locations WHERE code = ?", (str(code),)).fetchone()
        if row is not None:
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (int(row["id"]),))
    return report


def walk_out(conn, target: tuple[int, int] | None = None, *, edge: str = "", context: dict[str, Any] | None = None,
             plan: dict[str, Any] | None = None) -> dict[str, Any]:
    """Walk through the streets and out of town (playtest #71). Writes the walk.

    Returns {"left", "halted", "exit", "minutes", "report"}. A walk that must
    stop at a gate is written up to the gate and comes back with ``halted``
    ({"at", "why"}): the player has walked there. Raises ValueError (no way
    out) and PermissionError (too tired to walk it).
    """
    pos = get_position(conn)
    if plan is None:
        plan = plan_exit(conn, target, edge=edge, context=context)
    if plan.get("blocked"):
        raise PermissionError("Too exhausted to walk out of town. Wait, meditate, or sleep to recover energy.")
    halt = str(plan.get("halt") or "")
    if halt:
        plan = dict(plan, kind="walk", rule="town_walk")
    report = _commit_walk(conn, plan, pos, context)
    if report.get("blocked"):
        raise PermissionError("Too exhausted to walk out of town. Wait, meditate, or sleep to recover energy.")
    out = {"left": bool(report.get("left")), "exit": plan.get("exit"), "minutes": int(plan.get("minutes") or 0),
           "report": report, "halted": None}
    if halt:
        out["halted"] = {"at": str((plan.get("target") or {}).get("label") or (plan.get("target") or {}).get("name") or ""),
                         "why": halt}
    return out


def walk_to_cell(conn, cx: int, cy: int, *, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """A world-map pick of another cell of the same town: a walk through the streets, not a jump (#70, #71)."""
    chart = world_chart(conn)
    pos = get_position(conn)
    if chart is None or not pos:
        raise ValueError("You are not in a town.")
    city = city_by_id(chart, str(pos.get("city_id") or ""))
    if city is None:
        raise ValueError("You are not in a town.")
    view = _CityView(conn, chart, city, pos, _CellSource(conn, chart, generate=True))
    dest = (int(cx), int(cy))
    if dest not in view.cells:
        raise ValueError("That tile is not in this town.")
    town = view.source.get(*dest)
    if town is None:
        raise ValueError("That part of town is out of reach this turn.")
    goal = entry_tile(chart, city, view.cells[dest], town, (int(pos["cx"]), int(pos["cy"])))
    plan = _plan_walk(view, dest, {goal}, kind="walk", rule="town_walk",
                      target={"name": street_at(town, goal) or "the road", "cx": dest[0], "cy": dest[1]},
                      enter=False, context=context, budget=across_town_budget(city))
    if not plan.get("legs"):
        raise ValueError("No road you know leads there.")
    if plan.get("blocked"):
        raise PermissionError("Too exhausted to walk there. Wait, meditate, or sleep to recover energy.")
    report = _commit_walk(conn, plan, pos, context)
    return {"plan": {k: plan.get(k) for k in ("rule", "minutes", "partial", "remaining_minutes", "reached", "target")},
            "report": report, "position": get_position(conn)}


def plan_town_move(conn, chart: dict[str, Any], city: dict[str, Any], text: str, pos: dict[str, Any], *,
                   context: dict[str, Any] | None = None, generate: bool = True) -> dict[str, Any] | None:
    """This turn's town movement from the player's own words, or None when the line goes nowhere in town."""
    words = _player_words(text)
    low = _norm(words)
    if not low:
        return None
    from app import world as W

    doorway = W.venue_move_intent(words)
    moving = (
        W.travel_intent(words) or bool(doorway) or bool(_GO_RE.search(words)) or bool(_leave_asked(words))
        or bool(_TO_GATE_RE.search(words))
    )
    if not moving:
        return None
    source = _CellSource(conn, chart, generate=generate)
    view = _CityView(conn, chart, city, pos, source)
    here_town = view.town(int(pos["cx"]), int(pos["cy"]))
    if here_town is None:
        return None
    side = int(here_town["side"])
    here_i = _pos_index(pos, side)
    inside = str(pos.get("inside") or "")

    leave = _leave_asked(words)
    to_gate = None if leave or _LEAVE_RE.search(words) else _TO_GATE_RE.search(words)
    if leave:
        # The same exit planner as the Leave control and a map pick: in an
        # open town the nearest road out, in a walled one a gate (#71).
        named_gate = _GATE_COMPASS_RE.search(words)
        edge = _COMPASS_EDGE.get(str(named_gate.group("compass")).lower(), "") if named_gate else ""
        if not edge:
            named_side = re.search(r"\b(north|south|east|west)(?:ern)?\b", words, re.I)
            edge = _COMPASS_EDGE.get(named_side.group(1).lower(), "") if named_side else ""
        budget = across_town_budget(city)
        plan = _exit_walk(view, None, edge=edge, context=context, budget=budget) if edge else None
        if plan is None:
            plan = _exit_walk(view, None, context=context, budget=budget)
        if plan is not None:
            return plan
    if leave or to_gate:
        named_gate = _GATE_COMPASS_RE.search(words)
        gate = _gate_target(view, str(named_gate.group("compass")).lower()) if named_gate else None
        if gate is None:
            gate = _gate_target(view, "")  # no gate on that side: the nearest one
        if gate is not None:
            cx, cy, i, port = gate
            target = {"gate": str(port.get("gate") or ""), "name": f"the {port.get('gate')} gate", "cx": cx, "cy": cy,
                      "edge": str(port.get("edge") or "")}
            if leave:
                return _plan_walk(view, (cx, cy), {i}, kind="leave", rule="town_leave", target=target, enter=False,
                                  context=context)
            return _plan_walk(view, (cx, cy), {i}, kind="walk", rule="town_walk", target=target, enter=False,
                              context=context)

    enter = doorway == "enter"
    named = _plot_named(view, low)
    if named is not None:
        cx, cy, plot = named
        target = _target_entry(cx, cy, plot, side)
        f = plot.get("f")
        if f:
            tside = int(view.town(cx, cy)["side"])
            goals = {int(f[1]) * tside + int(f[0])}
            if inside and inside == str(plot["id"]):
                return None  # already inside it
            return _plan_walk(view, (cx, cy), goals, kind="enter" if enter else "walk",
                              rule="town_enter" if enter else "town_walk", target=target, enter=enter, context=context)

    word, kind = _trade_asked(low, _era(conn))
    if kind:
        # A door right here first: "enter the inn" at the inn's door.
        if enter:
            near = max(1, int(round(NEAR_METRES / tg.tile_metres(side))))
            dist = _road_dist(here_town, here_i, near)
            here_hits = []
            for i, d in dist.items():
                for plot in _ix(here_town)["front"].get(i) or []:
                    if _kind_matches(plot, kind):
                        here_hits.append((d, int(plot["n"]), plot))
            if here_hits:
                here_hits.sort(key=lambda h: h[:2])
                plot = here_hits[0][2]
                f = plot["f"]
                return _plan_walk(view, (int(pos["cx"]), int(pos["cy"])), {int(f[1]) * side + int(f[0])},
                                  kind="enter", rule="town_enter", target=_target_entry(int(pos["cx"]), int(pos["cy"]), plot, side),
                                  enter=True, context=context)
        how, found = find_kind(view, kind, lookup=generate)
        if found is None:
            return {
                "kind": "none" if how == "none" else "unknown",
                "rule": "town_none" if how == "none" else "town_unknown",
                "map_id": str(chart.get("id") or ""),
                "city_id": view.city_id,
                "trade": kind,
                "trade_label": venues.kind_label(kind),
                "minutes": 0,
                "legs": [],
                "enter": False,
                "blocked": False,
                "generated": list(source.made),
            }
        cx, cy, plot = found
        f = plot["f"]
        tside = int(view.town(cx, cy)["side"])
        plan = _plan_walk(view, (cx, cy), {int(f[1]) * tside + int(f[0])}, kind="enter" if enter else "walk",
                          rule="town_enter" if enter else "town_walk", target=_target_entry(cx, cy, plot, tside),
                          enter=enter, context=context)
        plan["found_by"] = how
        plan["generated"] = list(source.made)
        return plan

    street = _street_named(view, low)
    if street is not None:
        cx, cy, tiles, name = street
        return _plan_walk(view, (cx, cy), set(tiles), kind="walk", rule="town_walk",
                          target={"street": name, "name": name, "cx": cx, "cy": cy}, enter=False, context=context)
    ward = _ward_named(view, low)
    if ward is not None:
        cx, cy, district = ward
        town = source.get(cx, cy)
        if town is not None:
            anchor = district.get("anchor") or [0, 0]
            goal = nearest_road(town, int(anchor[0]), int(anchor[1]))
            if goal is not None:
                return _plan_walk(view, (cx, cy), {goal}, kind="walk", rule="town_walk",
                                  target={"ward": str(district.get("name") or ""), "name": str(district.get("name") or ""),
                                          "cx": cx, "cy": cy}, enter=False, context=context)

    if enter and not inside:
        here_plot = _frontage_plot(here_town, here_i)
        if here_plot is not None and here_plot.get("k") in _DOOR_KINDS:
            return _plan_walk(view, (int(pos["cx"]), int(pos["cy"])), {here_i}, kind="enter", rule="town_enter",
                              target=_target_entry(int(pos["cx"]), int(pos["cy"]), here_plot, side), enter=True,
                              context=context)
    if inside and doorway == "exit":
        return {
            "kind": "exit",
            "rule": "town_exit",
            "map_id": str(chart.get("id") or ""),
            "city_id": view.city_id,
            "from": {k: pos.get(k) for k in ("cx", "cy", "fx", "fy", "plot", "inside")},
            "target": {"name": "the street", "plot": inside},
            "legs": [{"cx": int(pos["cx"]), "cy": int(pos["cy"]), "side": side, "tiles": [here_i]}],
            "steps": 0,
            "minutes": 0,
            "partial": False,
            "remaining_minutes": 0,
            "end": (int(pos["cx"]), int(pos["cy"]), here_i),
            "heading": str(pos.get("heading") or ""),
            "reached": True,
            "enter": False,
            "blocked": False,
        }
    return None


def plan_to_plot(conn, chart: dict[str, Any], pos: dict[str, Any], plot_ref: str, *, enter: bool, rule: str,
                 context: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """A walk (and entry) to a plot in a generated cell, generating nothing (after the draft, TownGrid.md 5.2)."""
    found = locate_plot(conn, chart, plot_ref)
    if found is None:
        return None
    city, cell, town, plot = found
    if str(city.get("id") or "") != str(pos.get("city_id") or ""):
        return None
    f = plot.get("f")
    if not f:
        return None
    view = _CityView(conn, chart, city, pos, _CellSource(conn, chart, generate=False))
    side = int(town["side"])
    return _plan_walk(view, (int(cell["x"]), int(cell["y"])), {int(f[1]) * side + int(f[0])},
                      kind="enter" if enter else "walk", rule=rule,
                      target=_target_entry(int(cell["x"]), int(cell["y"]), plot, side), enter=enter, context=context)


# ---------------------------------------------------------------------------
# The draft's town block (TownGrid.md 5.3)
# ---------------------------------------------------------------------------

TOWN_RULE = (
    "The town's buildings are fixed. places_here are the ones beside the player. Going to or into one of them "
    "is MOVE with its name. A trade not listed may stand elsewhere in town; the engine walks there if the "
    "player asks. A building that is not listed and not asked for does not appear in the prose. Closed places "
    "cannot be entered."
)


def _places_here(conn, chart: dict[str, Any], city: dict[str, Any], town: dict[str, Any], i: int, heading: str,
                 know: _Knowledge, minute: int) -> list[dict[str, Any]]:
    side = int(town["side"])
    tmin = tg.tile_minutes(side)
    near = max(1, int(round(NEAR_METRES / tg.tile_metres(side))))
    limit = max(near, int(round(AROUND_MINUTES / tmin)))
    dist = _road_dist(town, i, limit)
    front = _ix(town)["front"]
    x0, y0 = i % side, i // side
    step = _HEADING_STEP.get(str(heading or ""))
    close: list[tuple[int, int, dict[str, Any]]] = []
    ahead: list[tuple[int, int, dict[str, Any]]] = []
    for j, d in dist.items():
        for plot in front.get(j) or ():
            if not know.kind_known(plot):
                continue
            if d <= near:
                close.append((d, int(plot["n"]), plot))
            elif plot.get("k") in _DOOR_KINDS and know.name_known(plot):
                fx, fy = j % side, j // side
                if step and ((fx - x0) * step[0] + (fy - y0) * step[1]) <= 0:
                    continue
                ahead.append((d, int(plot["n"]), plot))
    close.sort(key=lambda c: c[:2])
    ahead.sort(key=lambda c: c[:2])

    def entry(plot: dict[str, Any], d: int) -> dict[str, Any]:
        f = plot.get("f") or [x0, y0]
        named = know.name_known(plot)
        item: dict[str, Any] = {"name": str(plot.get("name") or "") if named else "", "kind": plot_label(plot)}
        if d == 0:
            item["where"] = "here"
        elif d <= near:
            item["where"] = f"a few steps {compass(int(f[0]) - x0, int(f[1]) - y0)}"
        else:
            item["where"] = f"{'ahead, ' if step else ''}{max(1, int(math.ceil(d * tmin)))} min {compass(int(f[0]) - x0, int(f[1]) - y0)}"
        if plot.get("vk"):
            item["open"] = _open_at(plot, minute)
            if not item["open"]:
                item["hours"] = _hours(plot)
        return item

    named_close = [c for c in close if know.name_known(c[2]) and c[2].get("k") in _NAMED_KINDS]
    out = [entry(c[2], c[0]) for c in named_close]
    out += [entry(c[2], c[0]) for c in ahead[:2]]
    if len(out) < 3:
        for c in close:
            if c in named_close:
                continue
            out.append(entry(c[2], c[0]))
            if len(out) >= PLACES_MAX:
                break
    if len(out) < PLACES_MAX:
        for c in ahead[2:]:
            out.append(entry(c[2], c[0]))
            if len(out) >= PLACES_MAX:
                break
    seen_names: set[str] = set()
    unique = []
    for item in out:
        key = item["name"] or f"{item['kind']}@{item['where']}"
        if key in seen_names:
            continue
        seen_names.add(key)
        unique.append(item)
    return unique[:PLACES_MAX]


def _streets_off(town: dict[str, Any], i: int) -> list[str]:
    side = int(town["side"])
    here = street_at(town, i)
    x, y = i % side, i // side
    out = []
    for (dx, dy), word in zip(_N4, ("north", "east", "south", "west")):
        nx, ny = x + dx, y + dy
        if not (0 <= nx < side and 0 <= ny < side) or not town["roads"][ny * side + nx]:
            continue
        j = ny * side + nx
        name = street_at(town, j)
        if town["roads"][j] == tg.ROAD_ALLEY and not name:
            out.append(f"an alley ({word})")
        elif name and name != here:
            out.append(f"{name} ({word})")
    return list(dict.fromkeys(out))[:4]


def town_contract(conn, chart: dict[str, Any], city: dict[str, Any], pos: dict[str, Any],
                  plan: dict[str, Any] | None) -> dict[str, Any] | None:
    """The movement_contract.town block for this turn, from the plan's end tile when it walks."""
    end_pos = dict(pos)
    walked = bool(plan and plan.get("legs") and not plan.get("blocked") and plan.get("kind") in ("walk", "enter", "leave"))
    extra: dict[tuple[int, int], tuple[set[int], set[int]]] = {}
    if walked:
        cx, cy, i = plan["end"]
        end_pos.update({"cx": cx, "cy": cy})
        town = tg.stored_cell(conn, chart, cx, cy)
        if town is None:
            return None
        end_pos.update({"fx": i % int(town["side"]), "fy": i // int(town["side"]), "heading": plan.get("heading") or ""})
        for k, leg in enumerate(plan["legs"]):
            leg_town = tg.stored_cell(conn, chart, int(leg["cx"]), int(leg["cy"]))
            if leg_town is not None:
                extra[(int(leg["cx"]), int(leg["cy"]))] = _sight(
                    leg_town, list(leg["tiles"]), plan.get("heading") if k == len(plan["legs"]) - 1 else ""
                )
    cx, cy = int(end_pos["cx"]), int(end_pos["cy"])
    town = tg.stored_cell(conn, chart, cx, cy)
    if town is None:
        return None
    side = int(town["side"])
    i = _pos_index(end_pos, side)
    located = tg._locate(chart, cx, cy)
    cell = located[1] if located else {}
    city_id = str(city.get("id") or "")
    roads_extra, read_extra = extra.get((cx, cy), (set(), set()))
    if not walked:
        roads_extra, read_extra = _sight(town, [i])
    know = _Knowledge(conn, chart, town, realized=_realized_rows(conn, city_id), claimed=_claimed_plots(conn, city_id),
                      extra_roads=roads_extra, extra_read=read_extra)
    minute = _world_minute(conn) + int((plan or {}).get("minutes") or 0 if walked else 0)
    ward = ward_at(town, cell, i)
    street = street_at(town, i)
    block: dict[str, Any] = {
        "name": str(city.get("name") or ""),
        "ward": (f"{ward.get('name')} ({str(ward.get('type') or '').replace('_', ' ')})" if ward.get("name") else ""),
        "street": street or ("an alley" if town["roads"][i] == tg.ROAD_ALLEY else "an unnamed lane"),
    }
    here_plot = _frontage_plot(town, i)
    if here_plot is not None and know.kind_known(here_plot) and here_plot.get("k") in _NAMED_KINDS:
        label = plot_label(here_plot)
        name = here_plot.get("name") if know.name_known(here_plot) else ""
        state = ""
        if here_plot.get("vk"):
            state = ", open" if _open_at(here_plot, minute) else ", closed"
        block["at"] = f"outside {name} ({label}{state})" if name else f"outside a {label}{state}"
    else:
        block["at"] = f"on {block['street']}"
    inside = ""
    if plan and plan.get("enter") and plan.get("target", {}).get("plot"):
        inside = str(plan["target"]["plot"])
    elif not walked and pos.get("inside") and not (plan and plan.get("kind") == "exit"):
        inside = str(pos.get("inside"))
    if inside:
        found = locate_plot(conn, chart, inside)
        if found is not None:
            block["inside"] = f"{found[3].get('name') or plot_label(found[3])} ({plot_label(found[3])})"
    block["places_here"] = _places_here(conn, chart, city, town, i, str(end_pos.get("heading") or ""), know, minute)
    off = _streets_off(town, i)
    if off:
        block["streets_off"] = off
    if plan:
        target = plan.get("target") or {}
        tname = str(target.get("name") or target.get("label") or "")
        if plan.get("blocked"):
            block["blocked"] = (
                f"The player is too tired to walk to {tname or 'there'}; they stay where they are."
                if "insufficient_energy" in (plan.get("reasons") or []) else "The player cannot walk there now."
            )
        elif plan.get("kind") in ("none", "unknown"):
            label = str(plan.get("trade_label") or "place of that trade")
            if plan.get("kind") == "none":
                block["none"] = f"No {label} stands in {city.get('name') or 'this town'}. Say so; do not produce one."
            else:
                block["none"] = f"No {label} is known nearby. The player can ask around; do not produce one."
        elif plan.get("kind") == "exit":
            block["arrived"] = "The player steps back out into the street."
        elif walked and plan.get("partial"):
            block["walking"] = {"to": tname, "minutes_left": int(plan.get("remaining_minutes") or 0)}
        elif walked or plan.get("kind") in ("walk", "enter", "leave"):
            arrived: dict[str, Any] = {"name": tname, "minutes": int(plan.get("minutes") or 0)}
            if plan.get("kind") == "leave":
                if target.get("checkpoint"):
                    arrived["where"] = "through the checkpoint, leaving town; the guards stop and question them first"
                elif target.get("gate"):
                    arrived["where"] = "at the gate, leaving town"
                else:
                    arrived["where"] = "at the edge of town, leaving it"
            elif plan.get("enter"):
                arrived["where"] = "goes inside"
            elif plan.get("enter_wanted") and not plan.get("open", True):
                arrived["where"] = "at the door; it is closed"
            else:
                arrived["where"] = "at the door" if target.get("plot") else "there"
            block["arrived"] = arrived
    block["rule"] = TOWN_RULE
    return block


# ---------------------------------------------------------------------------
# A turn: plan before the prompt, resolve, apply after the snapshot
# ---------------------------------------------------------------------------


def plan_turn(conn, text: str, *, input_kind: str = "player", context: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """The town side of one turn, before the prompt is built. Writes only town_cells cache rows."""
    chart = world_chart(conn)
    if chart is None:
        return None
    px, py = player_cell(chart)
    located = tg._locate(chart, px, py)
    pos = get_position(conn)
    if located is None:
        return {"clear": True} if pos else None
    city, cell = located
    town = tg.get_cell(conn, chart, px, py, create=True)
    if town is None:
        return None
    placed = None
    if (
        not pos
        or str(pos.get("map_id") or "") != str(chart.get("id") or "")
        or str(pos.get("city_id") or "") != str(city.get("id") or "")
        or (int(pos.get("cx", -1)), int(pos.get("cy", -1))) != (px, py)
    ):
        i = entry_tile(chart, city, cell, town, None)
        pos = _make_position(chart, city, px, py, town, i)
        placed = dict(pos)
    if pos.get("inside"):
        here = _current_location(conn)
        if here is None or str(here.get("plot_id") or "") != str(pos["inside"]):
            pos = dict(pos, inside="")
    plan = None
    locked = False
    try:
        from app import world as W

        locked = bool(W._map_is_locked(conn))
    except Exception:
        locked = False
    if input_kind == "player" and locked:
        # Confinement refuses any walk (docs/TownGrid.md 4.3).
        plan = {"kind": "stay", "rule": "town_locked", "legs": [], "minutes": 0, "enter": False, "blocked": True,
                "reasons": ["movement_locked"], "target": {}}
    elif input_kind == "player":
        try:
            plan = plan_town_move(conn, chart, city, text, pos, context=context)
        except Exception as exc:  # a planning bug must not cost the turn
            plan = {"kind": "error", "rule": "town_error", "error": f"{type(exc).__name__}: {exc}"[:200], "legs": [],
                    "minutes": 0, "enter": False, "blocked": False}
    try:
        contract = town_contract(conn, chart, city, pos, plan if plan and plan.get("kind") != "error" else None)
    except Exception:
        contract = None
    return {"position": pos, "placed": placed, "plan": plan, "contract": contract,
            "map_id": str(chart.get("id") or ""), "city_id": str(city.get("id") or "")}


_BUILDING_MOVE_KEYS = ("move_to_location", "move_to_location_code")


def _strip_unplotted_buildings(conn, chart: dict[str, Any], view: _CityView, result: dict[str, Any]) -> list[str]:
    """LOC_NEW rows that name a building the grid does not have are not stored (#55)."""
    dropped = []
    kept = []
    for location in result.get("locations") or []:
        if not isinstance(location, dict):
            kept.append(location)
            continue
        name = str(location.get("name") or "").strip()
        if name and venues.venue_kind_from_name(name) and _plot_named(view, _norm(name), known=False) is None:
            dropped.append(name)
            continue
        kept.append(location)
    if dropped:
        result["locations"] = kept
    return dropped


def _shown_entry_plot(view: _CityView, here_town: dict[str, Any], here_i: int, shown: dict[str, Any]) -> tuple[int, int, dict] | None:
    name = str(shown.get("name") or "")
    if name:
        found = _plot_named(view, _norm(name), known=False)
        if found is not None:
            return found
    kind = str(shown.get("kind") or "")
    side = int(here_town["side"])
    near = max(1, int(round(NEAR_METRES / tg.tile_metres(side))))
    dist = _road_dist(here_town, here_i, near)
    hits = []
    for j, d in dist.items():
        for plot in _ix(here_town)["front"].get(j) or ():
            if plot.get("k") not in _DOOR_KINDS:
                continue
            if kind and kind != "general_store" and str(plot.get("vk") or "") != kind:
                continue
            hits.append((d, int(plot["n"]), plot))
    if not hits:
        return None
    hits.sort(key=lambda h: h[:2])
    return int(view.pos["cx"]), int(view.pos["cy"]), hits[0][2]


# A door the prose walks through unasked is at most this many minutes away.
_NEAR_MINUTES = 2


def resolve_town_movement(conn, result: dict[str, Any], player_input: str, *, intent: str,
                          narration: str) -> dict[str, Any] | None:
    """resolve_movement in a plotted town (TownGrid.md 5.1-5.2). Edits only the turn dict; None means legacy rules.

    Never mints a building: a MOVE or an entry that names one the grid does
    not have is re-aimed at the real plot of that trade, or dropped.
    """
    from app import world as W

    town_turn = result.get("_town_turn") if isinstance(result.get("_town_turn"), dict) else None
    if town_turn and town_turn.get("clear"):
        return None
    pos = (town_turn or {}).get("position") or get_position(conn)
    if not pos:
        return None
    chart = world_chart(conn)
    if chart is None:
        return None
    located = tg._locate(chart, int(pos.get("cx", 0)), int(pos.get("cy", 0)))
    if located is None or str(located[0].get("id") or "") != str(pos.get("city_id") or ""):
        return None
    city, cell = located
    if town_turn is None:
        town_turn = {"position": pos, "plan": None, "placed": None}
        result["_town_turn"] = town_turn
    player_patch = result.get("player")
    if not isinstance(player_patch, dict):
        player_patch = {}
        result["player"] = player_patch
    current = _current_location(conn) or {}
    base = {"from": str(current.get("code") or "")}
    view = _CityView(conn, chart, city, pos, _CellSource(conn, chart, generate=False))
    here_town = view.town(int(pos["cx"]), int(pos["cy"]))
    if here_town is None:
        return None
    here_i = _pos_index(pos, int(here_town["side"]))
    plan = town_turn.get("plan")
    explicit_name = str(player_patch.get("move_to_location") or "").strip()
    explicit_code = str(player_patch.get("move_to_location_code") or "").strip()

    def clear_moves() -> None:
        for key in _BUILDING_MOVE_KEYS:
            player_patch[key] = None
        result["map_walk"] = None

    def report_for(p: dict[str, Any], status: str) -> dict[str, Any]:
        target = p.get("target") or {}
        rep = {
            **base,
            "status": status,
            "rule": p.get("rule") or "town_walk",
            "destination": str(target.get("name") or target.get("label") or ""),
            "minutes": int(p.get("minutes") or 0),
            "partial": bool(p.get("partial")),
            "blocked": bool(p.get("blocked")),
        }
        if p.get("enter_wanted") and not p.get("enter") and not p.get("open", True):
            rep["refused"] = "venue_closed"
        return rep

    dropped = _strip_unplotted_buildings(conn, chart, view, result)

    if plan and plan.get("kind") in ("walk", "enter", "exit", "leave"):
        clear_moves()
        if plan.get("enter"):
            player_patch["move_to_location"] = str((plan.get("target") or {}).get("name") or "")[:120] or None
        rep = report_for(plan, "repaired")
        if dropped:
            rep["dropped_buildings"] = dropped
        return rep
    if plan and plan.get("rule") == "town_locked":
        clear_moves()
        return {**base, "status": "refused", "rule": "town_locked", "blocked": True}
    if plan and plan.get("kind") in ("none", "unknown"):
        clear_moves()
        rep = {**base, "status": "unresolved", "rule": plan["rule"], "trade": plan.get("trade") or ""}
        if dropped:
            rep["dropped_buildings"] = dropped
        return rep

    unasked = ""
    if explicit_name or explicit_code or result.get("map_walk"):
        # Playtest #6c holds in town: a move the player did not ask for and the
        # prose does not show does not happen.
        rows = conn.execute("SELECT id, code, name, parent_id, kind FROM locations ORDER BY id").fetchall()
        unasked = W._unasked_unshown_move(result, player_patch, rows, player_input, intent=intent, narration=narration)
        if unasked:
            clear_moves()
            explicit_name = explicit_code = ""

    if explicit_name or explicit_code:
        name = explicit_name
        row = None
        if explicit_code:
            row = conn.execute("SELECT * FROM locations WHERE code = ? COLLATE NOCASE", (explicit_code.upper(),)).fetchone()
            if row is not None:
                name = str(row["name"] or "")
        if row is None and name:
            match = W._match_location_by_name(conn, W.humanize_place_name(name))
            if match is not None:
                row = W._location_row(conn, int(match["id"]))
            else:
                alias = W._alias_target(conn, W.humanize_place_name(name), "location")
                if alias:
                    row = conn.execute("SELECT * FROM locations WHERE code = ?", (alias,)).fetchone()
        if row is not None:
            row = dict(row)
            if str(row.get("plot_id") or ""):
                if str(row["plot_id"]) == str(pos.get("inside") or ""):
                    clear_moves()
                    return {**base, "status": "not_travel", "rule": "town_stay", "rejected": "same_place_name"}
                new_plan = plan_to_plot(conn, chart, pos, str(row["plot_id"]), enter=True, rule="town_enter")
                if new_plan is not None:
                    town_turn["plan"] = new_plan
                    clear_moves()
                    if new_plan.get("enter"):
                        player_patch["move_to_location"] = str(row.get("name") or "")[:120]
                    return report_for(new_plan, "model")
            elif str(row.get("city_id") or "") == str(city.get("id") or ""):
                # The town itself: from inside a building that is the way out.
                clear_moves()
                if pos.get("inside"):
                    town_turn["plan"] = {
                        "kind": "exit", "rule": "town_exit", "target": {"name": str(row.get("name") or "")},
                        "legs": [], "minutes": 0, "end": (int(pos["cx"]), int(pos["cy"]), here_i), "heading": pos.get("heading") or "",
                        "enter": False, "blocked": False, "partial": False, "reached": True,
                    }
                    return {**base, "status": "model", "rule": "town_exit", "destination": str(row.get("name") or "")}
                return {**base, "status": "not_travel", "rule": "town_stay", "rejected": "same_place_name"}
            elif not str(row.get("kind") or "") and not int(row.get("parent_id") or 0):
                return None  # a known place outside the grid: world travel, the legacy rules
            else:
                return None  # a venue from before this town had a grid
        found = _plot_named(view, _norm(name), known=False) if name else None
        if found is not None:
            new_plan = plan_to_plot(conn, chart, pos, str(found[2]["id"]), enter=True, rule="town_enter")
            if new_plan is not None:
                town_turn["plan"] = new_plan
                clear_moves()
                if new_plan.get("enter"):
                    player_patch["move_to_location"] = str(found[2].get("name") or "")[:120]
                return report_for(new_plan, "model")
        kind = venues.venue_kind_from_name(name) if name else ""
        if kind:
            kind = venues.kind_for_era(kind, _era(conn)) or kind
            how, near = find_kind(view, kind, lookup=False)
            clear_moves()
            if near is not None:
                new_plan = plan_to_plot(conn, chart, pos, str(near[2]["id"]), enter=True, rule="town_enter")
                if new_plan is not None and int(new_plan.get("minutes") or 0) > _NEAR_MINUTES:
                    # The prose was written with the door right there; a walk
                    # across town is not that scene (TownGrid.md 5.2).
                    return {**base, "status": "dropped", "rule": "town_far", "destination": name,
                            "prose_mismatch": name, "trade": kind, "far_minutes": int(new_plan.get("minutes") or 0)}
                if new_plan is not None:
                    town_turn["plan"] = new_plan
                    real = str(near[2].get("name") or "")
                    if new_plan.get("enter"):
                        player_patch["move_to_location"] = real[:120]
                    rep = report_for(new_plan, "repaired")
                    rep["renamed"] = {"from": name, "to": real}
                    text = W._narration_text(result)
                    invented = [n for n in dropped if _norm(n) != _norm(name)]
                    if real and name in text and not invented:
                        W._set_narration_text(result, text.replace(name, real))
                        rep["prose_renamed"] = True
                    else:
                        rep["prose_mismatch"] = name
                    return rep
            return {**base, "status": "dropped", "rule": "town_none" if how == "none" else "town_unknown",
                    "destination": name, "prose_mismatch": name}
        street = _street_named(view, _norm(name)) if name else None
        ward = _ward_named(view, _norm(name)) if name and street is None else None
        if street is not None or ward is not None:
            if street is not None:
                cx, cy, tiles, sname = street
                target = {"street": sname, "name": sname, "cx": cx, "cy": cy}
                goals = set(tiles)
            else:
                cx, cy, district = ward
                tw = view.town(cx, cy)
                if tw is None:
                    clear_moves()
                    return {**base, "status": "unresolved", "rule": "town_stay", "dropped": name}
                anchor = district.get("anchor") or [0, 0]
                goal = nearest_road(tw, int(anchor[0]), int(anchor[1]))
                goals = {goal} if goal is not None else set()
                target = {"ward": str(district.get("name") or ""), "name": str(district.get("name") or ""), "cx": cx, "cy": cy}
            if goals:
                new_plan = _plan_walk(view, (cx, cy), goals, kind="walk", rule="town_walk", target=target, enter=False,
                                      context=None)
                if new_plan.get("legs"):
                    town_turn["plan"] = new_plan
                    clear_moves()
                    return report_for(new_plan, "model")
        clear_moves()
        return {**base, "status": "unresolved", "rule": "town_stay", "dropped": name}

    # No MOVE: the prose may still walk the player through a door (TownGrid.md 5.2).
    if not pos.get("inside"):
        people = [str(r["name"] or "") for r in conn.execute(
            "SELECT name FROM npcs WHERE location_id = ?", (int(current.get("id") or 0),)
        ).fetchall()] if current else []
        shown = venues.entry_in_prose(narration, people)
        if shown:
            found = _shown_entry_plot(view, here_town, here_i, shown)
            result["map_walk"] = None
            if found is not None:
                new_plan = plan_to_plot(conn, chart, pos, str(found[2]["id"]), enter=True, rule="town_enter")
                if new_plan is not None and new_plan.get("minutes", 0) <= _NEAR_MINUTES:
                    town_turn["plan"] = new_plan
                    if new_plan.get("enter"):
                        player_patch["move_to_location"] = str(found[2].get("name") or "")[:120]
                    rep = report_for(new_plan, "repaired")
                    rep["rule"] = "town_shown"
                    rep["keeper"] = str(shown.get("keeper") or "")
                    rep["with"] = list(shown.get("with") or [])
                    return rep
            return {**base, "status": "unresolved", "rule": "town_shown_none",
                    "prose_mismatch": str(shown.get("name") or shown.get("noun") or "")}
    result["map_walk"] = None
    if unasked:
        return {**base, "status": "dropped_unshown", "rule": "town_stay", "destination": unasked, "intent": intent}
    travel = intent == "travel" or W.travel_intent(player_input)
    return {**base, "status": "unresolved" if travel else "not_travel", "rule": "town_stay"}


def apply_town_turn(conn, town_turn: dict[str, Any] | None, result: dict[str, Any], context: dict[str, Any] | None,
                    *, turn: int = 0) -> dict[str, Any] | None:
    """Write this turn's town move, after the rewind snapshot (TownGrid.md 5.1, 9).

    Preview, commit, advance: a blocked walk writes nothing. Returns a report.
    """
    if not town_turn:
        return None
    chart = world_chart(conn)
    if chart is None:
        return None
    if town_turn.get("clear"):
        clear_position(conn)
        return {"rule": "town_cleared"}
    pos = town_turn.get("position")
    if not pos:
        return None
    city = city_by_id(chart, str(pos.get("city_id") or ""))
    if city is None:
        return None
    report: dict[str, Any] = {}
    if town_turn.get("placed"):
        write_position(conn, pos)
        town = tg.stored_cell(conn, chart, int(pos["cx"]), int(pos["cy"]))
        if town is not None:
            roads, read = _sight(town, [_pos_index(pos, int(town["side"]))])
            tg.record_seen(conn, str(chart.get("id") or ""), int(pos["cx"]), int(pos["cy"]), int(town["side"]),
                           road_tiles=sorted(roads), plot_ns=sorted(read), turn=turn)
        settlement_row(conn, city, create=True)
        report["placed"] = {k: pos.get(k) for k in ("cx", "cy", "fx", "fy", "plot")}
    elif str((get_position(conn) or {}).get("inside") or "") != str(pos.get("inside") or ""):
        write_position(conn, pos)  # the building row it named is gone (a rewind, a load)
    plan = town_turn.get("plan")
    if not plan or plan.get("kind") not in ("walk", "enter", "exit", "leave"):
        return report or None
    report.update({"rule": plan.get("rule"), "minutes": int(plan.get("minutes") or 0), "partial": bool(plan.get("partial")),
                   "to": (plan.get("target") or {}).get("name") or ""})
    if plan.get("blocked"):
        report["blocked"] = True
        report["reasons"] = list(plan.get("reasons") or [])
        return report
    preview = _preview(conn, int(plan.get("minutes") or 0), context)
    if preview["blocked"]:
        report["blocked"] = True
        report["reasons"] = preview["reasons"]
        return report
    from app import world as W

    player_patch = result.get("player")
    if not isinstance(player_patch, dict):
        player_patch = {}
        result["player"] = player_patch
    settle = settlement_row(conn, city, create=True)
    settle_code = ""
    if settle:
        row = conn.execute("SELECT code FROM locations WHERE id = ?", (settle,)).fetchone()
        settle_code = str(row["code"] or "") if row else ""
    end = plan.get("end") or (int(pos["cx"]), int(pos["cy"]), _pos_index(pos, tg._side(tg._city_cells(city)[(int(pos["cx"]), int(pos["cy"]))])))
    cx, cy, i = int(end[0]), int(end[1]), int(end[2])
    town = tg.stored_cell(conn, chart, cx, cy)
    if town is None:
        report["blocked"] = True
        report["reasons"] = ["ungenerated"]
        return report
    new_pos = _make_position(chart, city, cx, cy, town, i, heading=str(plan.get("heading") or pos.get("heading") or ""))
    leaving = plan.get("kind") == "leave" and plan.get("reached")
    # Commit: position and marker.
    _set_marker(conn, chart, cx, cy)
    if plan.get("legs"):
        _record_walk_seen(conn, chart, plan["legs"], str(plan.get("heading") or ""), turn)
    # Advance: clock, weather, energy (the preview above passed).
    spent: dict[str, Any] = {}
    if int(plan.get("minutes") or 0) > 0:
        W._spend_travel(conn, {"minutes": int(plan["minutes"]), "terrain": "city"}, context, spent)
        if spent.get("time"):
            report["time"] = {"before": (spent["time"].get("before") or {}).get("label"),
                              "after": (spent["time"].get("after") or {}).get("label")}
    for key in _BUILDING_MOVE_KEYS:
        player_patch[key] = None
    if leaving:
        clear_position(conn)
        target = plan.get("target") or {}
        step = {"N": (0, -1), "S": (0, 1), "E": (1, 0), "W": (-1, 0)}.get(str(target.get("edge") or ""))
        if step:
            out_x, out_y = cx + step[0], cy + step[1]
            if tg._locate(chart, out_x, out_y) is None:
                try:
                    _set_marker(conn, chart, out_x, out_y)
                except Exception:
                    pass
        report["left"] = True
        if step:
            report["out"] = [cx + step[0], cy + step[1]]
        # Out of a building and out of town: the location is the town itself,
        # as after a world-map exit. story_walk_skips sees "left" and keeps the
        # story walk from heading back to this row's anchor, inside the town
        # (playtest #71: the player was walked back in at the south gate).
        if pos.get("inside") and settle_code:
            player_patch["move_to_location_code"] = settle_code
        return report
    target_plot = str((plan.get("target") or {}).get("plot") or "")
    if plan.get("enter") and target_plot:
        venue_id = realize_plot(conn, chart, target_plot)
        row = conn.execute("SELECT code, name FROM locations WHERE id = ?", (venue_id,)).fetchone() if venue_id else None
        if row is not None:
            new_pos["inside"] = target_plot
            player_patch["move_to_location_code"] = str(row["code"])
            report["entered"] = str(row["name"] or "")
    elif plan.get("enter_wanted") and plan.get("reached") and not plan.get("open", True) and target_plot:
        found = locate_plot(conn, chart, target_plot)
        if found is not None:
            note = f"{found[3].get('name') or plot_label(found[3])} is closed ({_hours(found[3])})."
            conn.execute("INSERT INTO journal (turn, kind, content) VALUES (?, ?, ?)", (turn, "venue_closed", note[:900]))
            report["refused"] = "venue_closed"
    if not new_pos.get("inside") and settle_code:
        here = _current_location(conn)
        if here is None or int(here.get("id") or 0) != settle:
            player_patch["move_to_location_code"] = settle_code
    write_position(conn, new_pos)
    return report


def story_walk_skips(conn, movement_report: dict[str, Any] | None, town_report: dict[str, Any] | None) -> bool:
    """plan_story_walk's town skip: the player is still in a town and the town rules moved (or kept) them.

    Also when the town rules just walked them out (``left``): the marker is
    already outside, and a story walk toward the town's own row would walk
    them straight back in (playtest #71).
    """
    if town_report and town_report.get("left"):
        return True
    if not get_position(conn):
        return False
    rule = str((movement_report or {}).get("rule") or "")
    return rule.startswith("town_") or bool(town_report and town_report.get("rule"))


# ---------------------------------------------------------------------------
# The click-walk (POST /api/town/walk)
# ---------------------------------------------------------------------------


def click_walk(conn, *, plot_ref: str = "", cx: int | None = None, cy: int | None = None, fx: int | None = None,
               fy: int | None = None, context: dict[str, Any] | None = None, travel_ready: bool = True) -> dict[str, Any]:
    """Walk to a plot's door or the road nearest a clicked tile, without going in (TownGrid.md 7).

    Raises ValueError (400) for a bad target, PermissionError (409) for a refused or blocked walk.
    """
    chart = world_chart(conn)
    pos = get_position(conn)
    if chart is None or not pos:
        raise ValueError("You are not in a town.")
    city = city_by_id(chart, str(pos.get("city_id") or ""))
    if city is None:
        raise ValueError("You are not in a town.")
    view = _CityView(conn, chart, city, pos, _CellSource(conn, chart, generate=True))
    if plot_ref:
        found = locate_plot(conn, chart, plot_ref)
        if found is None or str(found[0].get("id") or "") != str(city.get("id") or ""):
            raise ValueError("No plot you know of has that id.")
        _city, cell, town, plot = found
        know = view.know(int(cell["x"]), int(cell["y"]))
        if know is None or not know.kind_known(plot) or not plot.get("f"):
            raise ValueError("No plot you know of has that id.")
        dest = (int(cell["x"]), int(cell["y"]))
        side = int(town["side"])
        goals = {int(plot["f"][1]) * side + int(plot["f"][0])}
        target = _target_entry(dest[0], dest[1], plot, side)
        if not know.name_known(plot):
            target["name"] = ""  # a sign not yet read; the walk may read it
    else:
        if cx is None or cy is None or fx is None or fy is None:
            raise ValueError("Give a plot id or a tile.")
        dest = (int(cx), int(cy))
        if dest not in view.cells:
            raise ValueError("That tile is not in this town.")
        if f"{dest[0]},{dest[1]}" not in tg._seen_world_cells(chart):
            raise ValueError("You have not seen that part of town.")
        town = view.source.get(*dest)
        if town is None:
            raise ValueError("That part of town is out of reach this turn.")
        goal = nearest_road(town, int(fx), int(fy))
        if goal is None:
            raise ValueError("There is no road there.")
        goals = {goal}
        target = {"name": street_at(town, goal) or "the road", "cx": dest[0], "cy": dest[1]}
    # Walking to another cell of the same town is a walk, never long travel:
    # travel_ready no longer gates it (playtest #70; ``travel_ready`` is kept
    # for callers and ignored). Confinement is the route's own 409.
    plan = _plan_walk(view, dest, goals, kind="walk", rule="town_walk", target=target, enter=False, context=context)
    if not plan.get("legs"):
        raise ValueError("There is no road there.")
    if plan.get("blocked"):
        raise PermissionError("Too exhausted to walk there. Wait, meditate, or sleep to recover energy.")
    report = _commit_walk(conn, plan, pos, context)
    if plot_ref and not target.get("name"):
        # Reaching the door reads its sign; only then does the name go back.
        view._know.pop(dest, None)
        after = view.know(*dest)
        if after is not None and after.name_known(plot):
            target["name"] = str(plot.get("name") or "")
            if report.get("to") == "":
                report["to"] = target["name"]
    return {"plan": {k: plan.get(k) for k in ("rule", "minutes", "partial", "remaining_minutes", "reached", "target")},
            "report": report, "position": get_position(conn)}


def _turn(conn) -> int:
    try:
        row = conn.execute("SELECT value FROM pacing WHERE key = 'turn'").fetchone()
        return int(row["value"]) if row else 0
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Workplaces claim plots (TownGrid.md 4.4)
# ---------------------------------------------------------------------------


def npc_city(conn, chart: dict[str, Any] | None, home: Any) -> dict[str, Any] | None:
    """The plotted city an NPC's home location belongs to, or None."""
    if chart is None or home is None:
        return None
    city_id = str(venues._field(home, "city_id", "") or "")
    plot_ref = str(venues._field(home, "plot_id", "") or "")
    if not city_id and plot_ref:
        parsed = tg.parse_plot_id(plot_ref)
        city_id = parsed[0] if parsed else ""
    if not city_id:
        pos = get_position(conn)
        here = _current_location(conn)
        if pos and here is not None and int(here.get("id") or 0) == int(venues._field(home, "id", 0) or 0):
            city_id = str(pos.get("city_id") or "")
    return city_by_id(chart, city_id) if city_id else None


def claim_plot(conn, chart: dict[str, Any], city: dict[str, Any], kinds: list[str], npc_id: int) -> tuple[str, dict] | None:
    """(kind, plot) for an NPC of these trades: a free plot of the kind in a generated cell, else a claimed one."""
    city_id = str(city.get("id") or "")
    claimed = {pid for pid, nid in _claimed_plots(conn, city_id).items() if nid != int(npc_id)}
    kept = {
        str(r["plot_id"]) for r in conn.execute(
            "SELECT plot_id FROM locations WHERE COALESCE(plot_id, '') LIKE ? AND keeper_npc_id != 0 AND keeper_npc_id != ?",
            (f"{city_id}.%", int(npc_id)),
        ).fetchall()
    }
    pos = get_position(conn)
    if not pos or str(pos.get("city_id") or "") != city_id:
        cx, cy = int(city.get("x") or 0), int(city.get("y") or 0)
        pos = {"cx": cx, "cy": cy, "fx": 0, "fy": 0, "city_id": city_id}
    view = _CityView(conn, chart, city, pos, _CellSource(conn, chart, generate=False))
    for want in kinds:
        free = view.nearest(
            c for c in view.plots(known=False)
            if _kind_matches(c[2], want) and str(c[2]["id"]) not in claimed and str(c[2]["id"]) not in kept
        )
        if free is not None:
            return want, free[2]
    for want in kinds:
        taken = view.nearest(c for c in view.plots(known=False) if _kind_matches(c[2], want))
        if taken is not None:
            return want, taken[2]
    return None


def plan_plotted_workplace(conn, npc: Any, home: Any, kinds: list[str]) -> int | None:
    """plan_npc_workplace in a plotted city: claim a plot, or keep a nameless plan. None when not plotted.

    Planning never generates a cell and never makes a row. The return value is
    a realized plot's venue id, or 0.
    """
    chart = world_chart(conn)
    city = npc_city(conn, chart, home)
    if city is None or chart is None:
        return None
    npc_id = int(venues._field(npc, "id", 0) or 0)
    city_id = str(city.get("id") or "")
    current = {}
    try:
        current = json.loads(str(venues._field(npc, "workplace_plan", "") or "") or "{}")
    except (TypeError, ValueError):
        current = {}
    if isinstance(current, dict) and current.get("plot_id") and str(current.get("city_id") or "") == city_id:
        realized = conn.execute("SELECT id FROM locations WHERE plot_id = ?", (str(current["plot_id"]),)).fetchone()
        if realized is not None:
            conn.execute("UPDATE npcs SET workplace_id = ?, workplace_plan = '' WHERE id = ?", (int(realized["id"]), npc_id))
            return int(realized["id"])
        return 0
    settle = settlement_row(conn, city, create=False)
    claim = claim_plot(conn, chart, city, kinds, npc_id)
    if claim is not None:
        kind, plot = claim
        plan = {"kind": kind, "name": str(plot.get("name") or ""), "parent_id": settle, "plot_id": str(plot["id"]),
                "city_id": city_id}
        realized = conn.execute("SELECT id FROM locations WHERE plot_id = ?", (str(plot["id"]),)).fetchone()
        conn.execute(
            "UPDATE npcs SET workplace_plan = ?, workplace_plot = ? WHERE id = ?",
            (json.dumps(plan, ensure_ascii=True), str(plot["id"]), npc_id),
        )
        if realized is not None:
            conn.execute("UPDATE npcs SET workplace_id = ?, workplace_plan = '' WHERE id = ?", (int(realized["id"]), npc_id))
            return int(realized["id"])
        return 0
    plan = {"kind": kinds[0], "name": "", "parent_id": settle, "plot_id": "", "city_id": city_id}
    conn.execute(
        "UPDATE npcs SET workplace_plan = ?, workplace_plot = '' WHERE id = ?", (json.dumps(plan, ensure_ascii=True), npc_id)
    )
    return 0


def realize_workplace(conn, npc_id: int, plan: dict[str, Any]) -> int:
    """ensure_npc_workplace for a plotted plan: the plot's row with this NPC behind the counter; 0 when unclaimed."""
    plot_ref = str(plan.get("plot_id") or "")
    if not plot_ref:
        return 0
    chart = world_chart(conn)
    if chart is None:
        return 0
    venue_id = realize_plot(conn, chart, plot_ref)
    if not venue_id:
        return 0
    row = conn.execute("SELECT keeper_npc_id FROM locations WHERE id = ?", (venue_id,)).fetchone()
    if row is not None and not int(row["keeper_npc_id"] or 0):
        conn.execute("UPDATE locations SET keeper_npc_id = ? WHERE id = ?", (int(npc_id), venue_id))
    conn.execute("UPDATE npcs SET workplace_id = ?, workplace_plan = '' WHERE id = ?", (venue_id, int(npc_id)))
    return venue_id


# ---------------------------------------------------------------------------
# Told plots (TownGrid.md 6)
# ---------------------------------------------------------------------------


def record_told(conn, chart: dict[str, Any], place: dict[str, Any] | None, turn: int = 0) -> str:
    """A direction answer that pointed at a stall or a notice: remember it as told. Generates nothing."""
    if not isinstance(place, dict):
        return ""
    cx, cy = int(place.get("x") or 0), int(place.get("y") or 0)
    located = tg._locate(chart, cx, cy)
    if located is None:
        return ""
    city, cell = located
    kind = str(place.get("kind") or "")
    item = ""
    if kind == "stall":
        from app.local_intel import stalls_for_district
        from app.world_scale import theme_allows_slavery

        theme = str(chart.get("theme") or "")
        slavery = bool(chart.get("allows_slavery")) or theme_allows_slavery(theme)
        district = next((d for d in cell.get("districts") or [] if isinstance(d, dict)
                         and str(d.get("id") or "") == str(place.get("district_id") or "")), None)
        if district is None:
            return ""
        for index, stall in enumerate(stalls_for_district(cell, district, theme=theme, slavery=slavery)):
            if (int(stall["fine_x"]), int(stall["fine_y"])) == (int(place.get("fine_x") or 0), int(place.get("fine_y") or 0)):
                item = f"stall:{district.get('id')}:{index}"
                break
    elif kind == "notice":
        item = f"notice:{place.get('district_id')}"
    if not item:
        return ""
    tg.record_seen(conn, str(chart.get("id") or ""), cx, cy, tg._side(cell), told=[item], turn=turn)
    return item
