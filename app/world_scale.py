"""Seeded world grid. The land is 16,383 cells on a side. Cities are clumps on that grid.

Nothing here materializes 16,383² tiles. Wilderness is a pure function of the seed.
A city is a connected set of world cells inside a 9 by 9 neighborhood.
Eighty-one cells is the most a metropolis holds. The same count stretched
into a 1 by 81 line is rejected: the clump stays in that neighborhood.
A hamlet may be one cell. Any larger city is at least two cells wide at
its thickest row or column, and three when the run is seven or longer.
It leaves empty cells on its outer edge, and it keeps a one-cell branch,
so the outline is jagged rather than a solid block.
Each of those cells has its own internal grid, at most 128 by 128. The center
cell of a city that needs more than one cell is 128. Outer cells are smaller.
9 × 128 is 1,152, the widest fine span a city can reach.

City counts and sizes are rolled from a density percent. Prose does not place cities.
The preset chooses the wilderness, what that ground is made of, and which peoples
are usual when anyone lives there. A people-kind is a leaning, not a census.
"""

from __future__ import annotations

import math
import random
from typing import Any

# 14-bit coordinate space: valid cells are 0 .. 16382.
WORLD_SIDE = 16383
CITY_CELL_MAX = 128
CITY_SPAN_MAX = 9
CITY_FINE_MAX = CITY_SPAN_MAX * CITY_CELL_MAX  # 1152
PEOPLE_PER_FINE_TILE = 160
SIGNIFICANT_DISTRICT = 80

_BLOCKED = frozenset({"void", "water", "lava", "cliff", "mountain"})
_SHOP_TYPES = frozenset({"shopping", "food", "black_market", "craft"})
_ENTRY_TYPES = frozenset({"government", "military"})

_BASE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    "shopping": ("market", "food", "tools", "weapons", "cloth", "general"),
    "residential": ("housing",),
    "government": ("government", "records", "law"),
    "military": ("military", "weapons", "armor"),
    "food": ("food", "market"),
    "black_market": ("black_market", "weapons", "food", "drugs", "contraband"),
    "craft": ("tools", "weapons", "workshops"),
    "temple": ("worship",),
    "street": ("passage",),
}
_BLACK_MARKET_BUNDLE = ("black_market", "weapons", "food", "drugs", "contraband")

_DISTRICT_LABELS = {
    "shopping": "shopping",
    "residential": "housing",
    "government": "government",
    "military": "military",
    "food": "food",
    "black_market": "black market",
    "craft": "craft",
    "temple": "temple",
    "street": "street",
}
_DISTRICT_NAMES: dict[str, tuple[str, ...]] = {
    "shopping": ("Market Row", "Copper Market", "The Stalls", "Mercers' Way", "Cloth Hall"),
    "residential": ("Low Houses", "Hearth Ward", "Sleepers' Close", "The Burrows", "Lantern Streets"),
    "government": ("Crown Hall", "The Rolls", "Magistrate's Close", "Seal Court"),
    "military": ("The Barracks", "Shield Yard", "Watch Keep", "Spear Gate"),
    "food": ("Granary Ward", "Fish Market", "Baker's Row", "The Stores"),
    "black_market": ("The Undercroft", "Night Market", "Salt Thieves' Row", "The Pit"),
    "craft": ("Smiths' Quarter", "Tool Yard", "The Forges", "Wheel Street"),
    "temple": ("The Close", "Shrine Ward", "Candle Court"),
    "street": ("Main Way", "The Crossing", "Procession"),
}
_NAME_LEFT = (
    "Ash", "Bram", "Crow", "Dun", "Eld", "Fen", "Grey", "Har", "Ith", "Kest",
    "Lark", "Moor", "Nim", "Ost", "Pell", "Red", "Sable", "Thorn", "Vesper", "Wold",
)
_NAME_RIGHT = (
    "ford", "hold", "wick", "gate", "barrow", "mere", "spire", "watch", "haven",
    "mark", "fell", "reach", "yard", "rest", "crown",
)


def clamp_int(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(value)))


def normalize_density(value: Any) -> int:
    """Store density as 0–100. A fraction such as 0.58 is the same as 58."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0
    if 0 < number <= 1:
        number *= 100
    return clamp_int(int(round(number)), 0, 100)


def shops_for_density(density: Any, rng: random.Random) -> int:
    """50 density is 5 shops. Each point above a multiple of 10 is a 10% chance of one extra."""
    rank = normalize_density(density)
    base = rank // 10
    remainder = rank % 10
    extra = 1 if rng.random() < remainder * 0.1 else 0
    return base + extra


def mix_hash(seed: int, x: int, y: int, salt: int = 0) -> int:
    n = (
        int(seed) * 374761393
        + int(x) * 668265263
        + int(y) * 2147483647
        + int(salt) * 1274126177
    ) & 0xFFFFFFFF
    n = (n ^ (n >> 13)) * 1274126177 & 0xFFFFFFFF
    return (n ^ (n >> 16)) & 0xFFFFFFFF


def theme_key(preset: dict[str, Any] | None) -> str:
    preset = preset or {}
    age = str(preset.get("age") or "").strip().lower()
    env = str(preset.get("environment") or "").strip().lower()
    if age in {"post_collapse", "post-apocalyptic", "apocalyptic"} or env == "volcanic":
        return "post_collapse"
    if age in {"medieval", "ancient", "industrial", "far_future", "space_opera", "timeless", "mixed"}:
        return age
    if env in {"orbital", "deep_space"}:
        return "space_opera"
    return age or "mixed"


def theme_allows_slavery(theme: str) -> bool:
    """Black markets in these settings include a slave trade. Later settings do not."""
    return theme in {"medieval", "ancient", "mixed", "industrial", "post_collapse"}


def density_band(theme: str) -> tuple[int, int]:
    """Percent range the theme offers when nobody has supplied a number."""
    bands = {
        "post_collapse": (6, 16),
        "timeless": (8, 22),
        "space_opera": (10, 28),
        "ancient": (18, 36),
        "medieval": (28, 48),
        "mixed": (24, 44),
        "industrial": (36, 58),
        "far_future": (40, 64),
    }
    return bands.get(theme, (22, 42))


def advise_density_percent(theme: str, rng: random.Random) -> int:
    """A percent, not a layout. A model may replace this number later."""
    lo, hi = density_band(theme)
    return rng.randint(lo, hi)


def roll_large_city_count(density_percent: int, theme: str, rng: random.Random) -> int:
    """How many 7-to-9 span cities exist. A sparse theme caps that at 2."""
    p = normalize_density(density_percent) / 100
    if theme == "post_collapse":
        chance_two = 0.02 + 0.15 * p
        chance_one = 0.10 + 0.55 * p
        roll = rng.random()
        if roll < chance_two:
            return 2
        if roll < chance_two + chance_one:
            return 1
        return 0
    weight = 0.55 if theme in {"timeless", "space_opera"} else 1.0
    cap = 2 + int(p * 8 * weight)
    expected = (p ** 1.4) * 6 * weight
    count = 0
    while count < cap and expected > 0:
        if rng.random() < min(0.9, expected):
            count += 1
        expected -= 1
        if expected < 0.2 and count > 0:
            break
    return count


def settlement_count(density_percent: int, theme: str, rng: random.Random) -> int:
    p = normalize_density(density_percent) / 100
    count = 10 + int((p ** 0.7) * 70)
    if theme == "post_collapse":
        count = max(6, int(count * 0.55))
    elif theme in {"timeless", "space_opera"}:
        count = max(6, int(count * 0.7))
    return clamp_int(count + rng.randint(-2, 2), 4, 80)


def plan_city_scale(density_percent: int, theme: str, rng: random.Random) -> dict[str, Any]:
    """Turn one percent into the size band. The rolls, not the percent, pick each city."""
    p = normalize_density(density_percent) / 100
    sparse = theme == "post_collapse"
    average = 1 + p * (2.4 if sparse else 4.2)
    return {
        "density_percent": normalize_density(density_percent),
        "min_span": 1,
        "avg_span": round(average, 2),
        "max_span": CITY_SPAN_MAX,
        "max_ordinary_span": 4 if sparse else 6,
        "large_city_count": roll_large_city_count(density_percent, theme, rng),
        "settlement_count": settlement_count(density_percent, theme, rng),
    }


_NEIGHBORS = ((1, 0), (-1, 0), (0, 1), (0, -1))


def min_city_thickness(long_side: int) -> int:
    """How wide a city must be somewhere along a run of this length.

    One cell is a hamlet. A run of 2 to 6 is at least 2 wide. A run of 7
    to 9, the large-city band, is at least 3 wide. A 1-wide strip is never
    a city, including the 1 by 81 reading of a full metropolis.
    """
    long_side = int(long_side)
    if long_side <= 1:
        return 1
    if long_side >= 7:
        return 3
    return 2


def rim_gap_budget(width: int, height: int) -> int:
    """Empty cells required on the outer edge of the city's own span.

    A 4 by 4 span cannot be all 16 cells. It leaves 2 empty edge cells.
    Longer spans leave 3 or 4. Smaller multi-cell spans leave one.
    """
    width = max(0, int(width))
    height = max(0, int(height))
    area = width * height
    if area < 4:
        return 0
    if area < 16:
        return 1
    long_side = max(width, height)
    if long_side <= 5:
        return 2
    if long_side <= 7:
        return 3
    return 4


def _connected(cells: set[tuple[int, int]]) -> bool:
    if not cells:
        return False
    start = next(iter(cells))
    seen = {start}
    stack = [start]
    while stack:
        x, y = stack.pop()
        for dx, dy in _NEIGHBORS:
            nxt = (x + dx, y + dy)
            if nxt in cells and nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return len(seen) == len(cells)


def _degree(cell: tuple[int, int], cells: set[tuple[int, int]]) -> int:
    x, y = cell
    return sum((x + dx, y + dy) in cells for dx, dy in _NEIGHBORS)


def _has_spur(cells: set[tuple[int, int]]) -> bool:
    """A branch end: one occupied cell with a single street-neighbor."""
    if len(cells) <= 1:
        return True
    return any(_degree(cell, cells) == 1 for cell in cells)


def _tight_bounds(cells: set[tuple[int, int]]) -> tuple[int, int, int, int]:
    xs = [x for x, _y in cells]
    ys = [y for _x, y in cells]
    return min(xs), min(ys), max(xs), max(ys)


def _cross_thickness(cells: set[tuple[int, int]]) -> int:
    rows: dict[int, int] = {}
    cols: dict[int, int] = {}
    for x, y in cells:
        rows[y] = rows.get(y, 0) + 1
        cols[x] = cols.get(x, 0) + 1
    return max(max(rows.values()), max(cols.values()))


def _thickness_ok(cells: set[tuple[int, int]], box_w: int, box_h: int) -> bool:
    if box_w * box_h <= 1:
        return True
    if len(cells) <= 1:
        return False
    x0, y0, x1, y1 = _tight_bounds(cells)
    span_w = x1 - x0 + 1
    span_h = y1 - y0 + 1
    if min(box_w, box_h) >= 2 and min(span_w, span_h) < 2:
        return False
    long_side = max(span_w, span_h)
    need = min(min_city_thickness(long_side), min(box_w, box_h), long_side)
    return _cross_thickness(cells) >= need


def _rim_gaps(cells: set[tuple[int, int]]) -> int:
    if not cells:
        return 0
    x0, y0, x1, y1 = _tight_bounds(cells)
    gaps = 0
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            if (x in (x0, x1) or y in (y0, y1)) and (x, y) not in cells:
                gaps += 1
    return gaps


def _inside(cell: tuple[int, int], width: int, height: int) -> bool:
    return 0 <= cell[0] < width and 0 <= cell[1] < height


def _accept(trial: set[tuple[int, int]], center: tuple[int, int], box_w: int, box_h: int) -> bool:
    return center in trial and _connected(trial) and _thickness_ok(trial, box_w, box_h)


def _thicken(
    rng: random.Random,
    cells: set[tuple[int, int]],
    width: int,
    height: int,
) -> None:
    guard = 0
    limit = width * height
    while not _thickness_ok(cells, width, height) and guard < limit:
        guard += 1
        options: list[tuple[int, int]] = []
        for x, y in cells:
            for dx, dy in _NEIGHBORS:
                nxt = (x + dx, y + dy)
                if not _inside(nxt, width, height) or nxt in cells:
                    continue
                trial = set(cells)
                trial.add(nxt)
                if _thickness_ok(trial, width, height) or _cross_thickness(trial) > _cross_thickness(cells):
                    options.append(nxt)
        if not options:
            break
        ready = [cell for cell in options if _thickness_ok(set(cells) | {cell}, width, height)]
        cells.add(rng.choice(ready or options))


def _open_rim(
    rng: random.Random,
    cells: set[tuple[int, int]],
    width: int,
    height: int,
    center: tuple[int, int],
    protect: set[tuple[int, int]],
) -> None:
    guard = 0
    limit = width * height
    while guard < limit:
        guard += 1
        x0, y0, x1, y1 = _tight_bounds(cells)
        if _rim_gaps(cells) >= rim_gap_budget(x1 - x0 + 1, y1 - y0 + 1):
            return
        corners: list[tuple[int, int]] = []
        edges: list[tuple[int, int]] = []
        for x, y in cells:
            if (x, y) == center or (x, y) in protect:
                continue
            on_x = x in (x0, x1)
            on_y = y in (y0, y1)
            if on_x and on_y:
                corners.append((x, y))
            elif on_x or on_y:
                edges.append((x, y))
        rng.shuffle(corners)
        rng.shuffle(edges)
        removed = False
        for cell in corners + edges:
            trial = set(cells)
            trial.remove(cell)
            if not trial or not _accept(trial, center, width, height):
                continue
            cells.remove(cell)
            removed = True
            break
        if not removed:
            return


def _ensure_spur(
    rng: random.Random,
    cells: set[tuple[int, int]],
    width: int,
    height: int,
    center: tuple[int, int],
) -> tuple[int, int] | None:
    if _has_spur(cells):
        for cell in sorted(cells):
            if _degree(cell, cells) == 1:
                return cell
        return None
    candidates: list[tuple[int, int]] = []
    for x, y in cells:
        for dx, dy in _NEIGHBORS:
            nxt = (x + dx, y + dy)
            if not _inside(nxt, width, height) or nxt in cells:
                continue
            if _degree(nxt, cells) == 1:
                candidates.append(nxt)
    if candidates:
        spur = rng.choice(candidates)
        cells.add(spur)
        return spur
    rim = [cell for cell in cells if cell != center]
    rng.shuffle(rim)
    for leaf in rim:
        neighbors = [
            (leaf[0] + dx, leaf[1] + dy)
            for dx, dy in _NEIGHBORS
            if (leaf[0] + dx, leaf[1] + dy) in cells
        ]
        if len(neighbors) < 2:
            continue
        for keep in neighbors:
            trial = set(cells)
            for neighbor in neighbors:
                if neighbor != keep and neighbor != center:
                    trial.discard(neighbor)
            if leaf not in trial or not _accept(trial, center, width, height):
                continue
            if _degree(leaf, trial) != 1:
                continue
            cells.clear()
            cells.update(trial)
            return leaf
    return None


def clump_shape_ok(cells: set[tuple[int, int]], box_w: int, box_h: int) -> bool:
    """The grown footprint obeys the spread, edge, and branch limits."""
    center = (int(box_w) // 2, int(box_h) // 2)
    if center not in cells or not _connected(cells):
        return False
    if int(box_w) * int(box_h) <= 1:
        return cells == {center}
    if not _thickness_ok(cells, box_w, box_h) or not _has_spur(cells):
        return False
    x0, y0, x1, y1 = _tight_bounds(cells)
    span_w = x1 - x0 + 1
    span_h = y1 - y0 + 1
    if len(cells) >= span_w * span_h:
        return False
    return _rim_gaps(cells) >= rim_gap_budget(span_w, span_h)


def _conform_clump(
    rng: random.Random,
    cells: set[tuple[int, int]],
    width: int,
    height: int,
) -> set[tuple[int, int]]:
    """Thick enough, missing part of its outline, and branched."""
    center = (width // 2, height // 2)
    cells.add(center)
    if width * height <= 1:
        return cells
    _thicken(rng, cells, width, height)
    spur = _ensure_spur(rng, cells, width, height, center)
    protect = {spur} if spur is not None else set()
    _open_rim(rng, cells, width, height, center, protect)
    if not _has_spur(cells):
        spur = _ensure_spur(rng, cells, width, height, center)
        protect = {spur} if spur is not None else protect
        _open_rim(rng, cells, width, height, center, protect)
    if not _thickness_ok(cells, width, height):
        _thicken(rng, cells, width, height)
    return cells


def grow_connected(rng: random.Random, width: int, height: int) -> set[tuple[int, int]]:
    """A clump inside the box. The center stays. The outline is not a solid block."""
    width = max(1, int(width))
    height = max(1, int(height))
    cx, cy = width // 2, height // 2
    cells = {(cx, cy)}
    area = width * height
    if area <= 3:
        target = area
    else:
        target = rng.randint(max(1, int(area * 0.5)), max(1, int(area * 0.82)))
    frontier = [(cx, cy)]
    guard = 0
    while len(cells) < target and frontier and guard < area * 8:
        guard += 1
        index = rng.randrange(len(frontier))
        x, y = frontier[index]
        options = []
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nxt = (x + dx, y + dy)
            if 0 <= nxt[0] < width and 0 <= nxt[1] < height and nxt not in cells:
                options.append(nxt)
        if not options:
            frontier.pop(index)
            continue
        nxt = rng.choice(options)
        if rng.random() < 0.8 or len(cells) < max(4, area // 5):
            cells.add(nxt)
            frontier.append(nxt)
    stalled = 0
    while len(cells) < target and stalled < area:
        grew = False
        for x, y in list(cells):
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nxt = (x + dx, y + dy)
                if 0 <= nxt[0] < width and 0 <= nxt[1] < height and nxt not in cells:
                    cells.add(nxt)
                    grew = True
                    break
            if len(cells) >= target:
                break
        if not grew:
            break
        stalled += 1
    return _conform_clump(rng, cells, width, height)


def choose_box(
    rng: random.Random,
    *,
    large: bool,
    max_ordinary: int,
    target_fine: int,
) -> tuple[int, int, int | None]:
    """Bounding box, plus the internal side when the whole city fits in one cell."""
    target_fine = max(8, int(target_fine))
    if not large and target_fine <= CITY_CELL_MAX:
        return 1, 1, target_fine
    long = max(1, math.ceil(target_fine / CITY_CELL_MAX))
    long = min(CITY_SPAN_MAX, long)
    if large:
        long = min(CITY_SPAN_MAX, max(7, long))
    else:
        long = min(max(2, int(max_ordinary)), max(2, long))
    floor = min_city_thickness(long)
    short = rng.randint(floor, long)
    if rng.random() < 0.5:
        return long, short, None
    return short, long, None


def roll_target_fine(rng: random.Random, *, large: bool, avg_span: float) -> int:
    if large:
        return rng.randint(CITY_CELL_MAX * 5, CITY_FINE_MAX)
    mean = 16 + float(avg_span) * 36
    return int(rng.triangular(8, CITY_CELL_MAX * 3, mean))


def _internal_sides(
    local: set[tuple[int, int]],
    box_w: int,
    box_h: int,
    single_side: int | None,
    rng: random.Random,
) -> dict[tuple[int, int], int]:
    cx, cy = box_w // 2, box_h // 2
    max_dist = max(max(abs(x - cx), abs(y - cy)) for x, y in local)
    sides: dict[tuple[int, int], int] = {}
    if max_dist <= 0:
        sides[(cx, cy)] = clamp_int(int(single_side or 24), 8, CITY_CELL_MAX)
        return sides
    for x, y in local:
        dist = max(abs(x - cx), abs(y - cy))
        if dist == 0:
            sides[(x, y)] = CITY_CELL_MAX
            continue
        falloff = dist / max_dist
        side = int(round(CITY_CELL_MAX * (1 - 0.62 * falloff))) + rng.randint(-6, 4)
        sides[(x, y)] = clamp_int(side, 8, CITY_CELL_MAX - 16)
    return sides


def city_peak_density(footprint: int, widest_side: int, rng: random.Random) -> int:
    """Bigger cities peak higher. The peak is not forced to 100."""
    size = min(1.0, (max(1, footprint) * max(1, widest_side)) / (81 * CITY_CELL_MAX))
    base = 16 + int(74 * (size ** 0.65))
    return clamp_int(base + rng.randint(-5, 5), 8, 92)


def cell_density(peak: int, dist: int, max_dist: int, rng: random.Random) -> int:
    """The center cell keeps the peak. Outer cells stay strictly below it, and nothing is forced to 100."""
    peak = clamp_int(peak, 1, 92)
    if max_dist <= 0 or dist <= 0:
        return peak
    falloff = dist / max_dist
    base = peak * (1 - 0.55 * falloff)
    return clamp_int(int(round(base)) + rng.randint(-3, 3), 1, peak - 1)


def population_of(cells: list[dict[str, Any]]) -> int:
    total = 0
    for cell in cells:
        side = int(cell.get("side") or 0)
        density = normalize_density(cell.get("density") or 0)
        factor = 0.2 + 0.8 * (density / 100)
        total += int(side * side * factor * PEOPLE_PER_FINE_TILE)
    return total


def population_band(population: int) -> str:
    if population < 2_000:
        return "hamlet"
    if population < 15_000:
        return "village"
    if population < 80_000:
        return "town"
    if population < 1_500_000:
        return "city"
    if population < 20_000_000:
        return "large_city"
    return "metropolis"


def street_mask(seed: int, side: int) -> set[tuple[int, int]]:
    if side < 24:
        return set()
    streets: set[tuple[int, int]] = set()
    mid = side // 2
    for index in range(side):
        streets.add((mid, index))
        streets.add((index, mid))
    if side >= 48:
        shift = 4 + (mix_hash(seed, side, 1) % max(1, side // 3))
        for index in range(side):
            streets.add((min(side - 1, shift), index))
    return streets


def choose_district_types(side: int, rng: random.Random) -> list[str]:
    if side < 20:
        return [rng.choice(("residential", "shopping", "food"))]
    types = ["residential", "shopping"]
    if side >= 28:
        types.append("food")
    if side >= 40:
        types.extend(("craft", "residential"))
    if side >= 64:
        types.extend(("government", "military", "black_market", "food"))
    if side >= 96 and rng.random() < 0.7:
        types.append("temple")
    return types


def _pick_anchor(
    rng: random.Random,
    side: int,
    streets: set[tuple[int, int]],
    taken: set[tuple[int, int]],
    kind: str,
) -> tuple[int, int]:
    center = (side - 1) / 2
    for _ in range(48):
        if kind in {"government", "shopping", "temple"}:
            spread = max(1, side // 5)
            x = int(round(center + rng.randint(-spread, spread)))
            y = int(round(center + rng.randint(-spread, spread)))
        elif kind in {"black_market", "military"}:
            edge = max(1, side // 6)
            x = rng.choice((rng.randrange(edge), side - 1 - rng.randrange(edge)))
            y = rng.randrange(side)
        else:
            x = rng.randrange(side)
            y = rng.randrange(side)
        x = clamp_int(x, 0, side - 1)
        y = clamp_int(y, 0, side - 1)
        if (x, y) not in streets and (x, y) not in taken:
            return x, y
    for y in range(side):
        for x in range(side):
            if (x, y) not in streets and (x, y) not in taken:
                return x, y
    return 0, 0


def _flood(side: int, streets: set[tuple[int, int]], anchors: list[tuple[int, int]]) -> dict[tuple[int, int], int]:
    owner: dict[tuple[int, int], int] = {}
    queue: list[tuple[int, int]] = []
    for index, anchor in enumerate(anchors):
        if anchor in streets or not (0 <= anchor[0] < side and 0 <= anchor[1] < side):
            continue
        owner[anchor] = index
        queue.append(anchor)
    head = 0
    while head < len(queue):
        x, y = queue[head]
        head += 1
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            nxt = (x + dx, y + dy)
            if nxt in streets or nxt in owner:
                continue
            if 0 <= nxt[0] < side and 0 <= nxt[1] < side:
                owner[nxt] = owner[(x, y)]
                queue.append(nxt)
    return owner


def _entrances(
    tiles: list[tuple[int, int]],
    owner: dict[tuple[int, int], int],
    streets: set[tuple[int, int]],
    index: int,
    rng: random.Random,
) -> list[dict[str, int]]:
    if len(tiles) < SIGNIFICANT_DISTRICT:
        return []
    borders: list[tuple[int, int]] = []
    for x, y in tiles:
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            nxt = (x + dx, y + dy)
            if nxt in streets or (nxt in owner and owner[nxt] != index):
                borders.append((x, y))
                break
    if not borders:
        return []
    rng.shuffle(borders)
    count = 1 if len(tiles) < 200 else (2 if len(tiles) < 600 else 3)
    return [{"x": x, "y": y} for x, y in borders[:count]]


def _permissions(kind: str, *, slavery: bool, black_market: bool) -> list[str]:
    if kind == "black_market" or black_market:
        perms = list(_BLACK_MARKET_BUNDLE)
        if slavery:
            perms.append("slavery")
        if kind != "black_market":
            for item in _BASE_PERMISSIONS.get(kind, ()):
                if item not in perms:
                    perms.append(item)
        return perms
    return list(_BASE_PERMISSIONS.get(kind, ("general",)))


def layout_districts(
    rng: random.Random,
    *,
    side: int,
    seed: int,
    cell_density_value: int,
    slavery: bool,
) -> list[dict[str, Any]]:
    side = clamp_int(side, 1, CITY_CELL_MAX)
    streets = street_mask(seed, side)
    kinds = choose_district_types(side, rng)
    taken: set[tuple[int, int]] = set()
    anchors: list[tuple[int, int]] = []
    for kind in kinds:
        anchor = _pick_anchor(rng, side, streets, taken, kind)
        taken.add(anchor)
        anchors.append(anchor)
    owner = _flood(side, streets, anchors)
    groups: list[list[tuple[int, int]]] = [[] for _ in kinds]
    for pos, index in owner.items():
        groups[index].append(pos)
    used_names: set[str] = set()
    districts: list[dict[str, Any]] = []
    center = (side - 1) / 2
    for index, kind in enumerate(kinds):
        tiles = groups[index]
        if not tiles:
            continue
        anchor = anchors[index]
        falloff = max(abs(anchor[0] - center), abs(anchor[1] - center)) / max(1, side / 2)
        bias = {
            "shopping": 6, "government": 4, "military": 2, "food": 0, "craft": 0,
            "residential": -4, "black_market": -2, "temple": 0,
        }.get(kind, 0)
        density = clamp_int(cell_density_value + bias - int(10 * falloff) + rng.randint(-2, 2), 0, 96)
        grant_market = kind == "shopping" and side >= 48 and rng.random() < 0.2
        perms = _permissions(kind, slavery=slavery, black_market=grant_market)
        name = _unique_name(rng.choice(_DISTRICT_NAMES.get(kind, ("Ward",))), used_names)
        requires_entry = kind in _ENTRY_TYPES
        districts.append(
            {
                "id": f"d{index}",
                "type": kind,
                "label": _DISTRICT_LABELS.get(kind, kind),
                "name": name,
                "anchor": [anchor[0], anchor[1]],
                "density": density,
                "permissions": perms,
                "shop_count": shops_for_density(density, rng) if kind in _SHOP_TYPES else 0,
                "tile_count": len(tiles),
                "requires_entry": requires_entry,
                "entrances": _entrances(tiles, owner, streets, index, rng) if requires_entry else [],
            }
        )
    if streets:
        name = _unique_name(rng.choice(_DISTRICT_NAMES["street"]), used_names)
        districts.append(
            {
                "id": "street",
                "type": "street",
                "label": "street",
                "name": name,
                "anchor": [side // 2, side // 2],
                "density": clamp_int(cell_density_value - 8, 0, 96),
                "permissions": ["passage"],
                "shop_count": 0,
                "tile_count": len(streets),
                "requires_entry": False,
                "entrances": [],
            }
        )
    return districts


def _unique_name(name: str, used: set[str]) -> str:
    base = name
    candidate = base
    number = 2
    while candidate.lower() in used:
        candidate = f"{base} {number}"
        number += 1
    used.add(candidate.lower())
    return candidate


def tiles_in_cell(cell: dict[str, Any]) -> list[dict[str, Any]]:
    """Rebuild the internal grid from the stored anchors. Names stay on the district."""
    side = clamp_int(int(cell.get("side") or 1), 1, CITY_CELL_MAX)
    seed = int(cell.get("seed") or 1)
    streets = street_mask(seed, side)
    stored = [item for item in (cell.get("districts") or []) if isinstance(item, dict)]
    bodies = [item for item in stored if item.get("type") != "street"]
    street = next((item for item in stored if item.get("type") == "street"), None)
    anchors = []
    for item in bodies:
        anchor = item.get("anchor") or [0, 0]
        anchors.append((int(anchor[0]), int(anchor[1])))
    owner = _flood(side, streets, anchors)
    tiles: list[dict[str, Any]] = []
    for y in range(side):
        for x in range(side):
            if (x, y) in streets and street is not None:
                district = street
            elif (x, y) in owner and owner[(x, y)] < len(bodies):
                district = bodies[owner[(x, y)]]
            elif bodies:
                district = bodies[0]
            else:
                continue
            tiles.append(
                {
                    "x": x,
                    "y": y,
                    "type": district.get("type"),
                    "label": district.get("label") or district.get("type"),
                    "name": district.get("name") or "",
                    "permissions": list(district.get("permissions") or []),
                    "requires_entry": bool(district.get("requires_entry")),
                }
            )
    return tiles


def cell_raster(cell: dict[str, Any], res: int) -> list[list[int]]:
    """The internal grid sampled down to res by res, as indexes into cell["districts"].

    Same flood as tiles_in_cell, without one dict per fine tile, so a whole
    city can be drawn. -1 is ground no district owns.
    """
    side = clamp_int(int(cell.get("side") or 1), 1, CITY_CELL_MAX)
    res = clamp_int(int(res), 1, side)
    seed = int(cell.get("seed") or 1)
    streets = street_mask(seed, side)
    stored = [item for item in (cell.get("districts") or []) if isinstance(item, dict)]
    body_index = [index for index, item in enumerate(stored) if item.get("type") != "street"]
    street_index = next((index for index, item in enumerate(stored) if item.get("type") == "street"), -1)
    anchors = []
    for index in body_index:
        anchor = stored[index].get("anchor") or [0, 0]
        anchors.append((int(anchor[0]), int(anchor[1])))
    owner = _flood(side, streets, anchors)
    fallback = body_index[0] if body_index else -1
    rows: list[list[int]] = []
    for ry in range(res):
        fy = min(side - 1, int((ry + 0.5) * side / res))
        row: list[int] = []
        for rx in range(res):
            fx = min(side - 1, int((rx + 0.5) * side / res))
            if (fx, fy) in streets and street_index >= 0:
                row.append(street_index)
            elif (fx, fy) in owner and owner[(fx, fy)] < len(body_index):
                row.append(body_index[owner[(fx, fy)]])
            else:
                row.append(fallback)
        rows.append(row)
    return rows


def _place_name(rng: random.Random, band: str, used: set[str]) -> str:
    base = f"{rng.choice(_NAME_LEFT)}{rng.choice(_NAME_RIGHT)}"
    if band == "metropolis":
        base = f"{base} Crown"
    elif band in {"large_city", "city"}:
        base = f"{base}"
    return _unique_name(base, used)


def _world_state_for_band(band: str) -> str:
    if band in {"metropolis", "large_city", "city"}:
        return "city"
    if band == "town":
        return "town"
    return "village"


def build_city(
    rng: random.Random,
    *,
    origin: tuple[int, int],
    box_w: int,
    box_h: int,
    single_side: int | None,
    slavery: bool,
    name: str = "",
    city_id: str = "",
) -> dict[str, Any]:
    local = grow_connected(rng, box_w, box_h)
    city = _city_from_local(
        rng,
        origin=origin,
        local=local,
        box_w=box_w,
        box_h=box_h,
        single_side=single_side,
        slavery=slavery,
        used_names=set(),
        city_id=city_id,
    )
    if name:
        city["name"] = name
    return city


def _fine_span(cells: list[dict[str, Any]]) -> int:
    if not cells:
        return 0
    by_row: dict[int, int] = {}
    by_col: dict[int, int] = {}
    for cell in cells:
        local = cell.get("local") or [0, 0]
        by_row[int(local[1])] = by_row.get(int(local[1]), 0) + int(cell["side"])
        by_col[int(local[0])] = by_col.get(int(local[0]), 0) + int(cell["side"])
    return max(max(by_row.values()), max(by_col.values()))


def _overlaps(cells: set[tuple[int, int]], occupied: set[tuple[int, int]], gap: int) -> bool:
    if not occupied:
        return False
    for x, y in cells:
        for dy in range(-gap, gap + 1):
            for dx in range(-gap, gap + 1):
                if max(abs(dx), abs(dy)) <= gap and (x + dx, y + dy) in occupied:
                    return True
    return False


def _stamp_city(
    rng: random.Random,
    *,
    occupied: set[tuple[int, int]],
    large: bool,
    plan: dict[str, Any],
    slavery: bool,
    used_names: set[str],
    city_id: str,
    gap: int,
) -> dict[str, Any] | None:
    target = roll_target_fine(rng, large=large, avg_span=float(plan.get("avg_span") or 1))
    for _attempt in range(40):
        box_w, box_h, single_side = choose_box(
            rng,
            large=large,
            max_ordinary=int(plan.get("max_ordinary_span") or 6),
            target_fine=target,
        )
        if box_w > WORLD_SIDE or box_h > WORLD_SIDE:
            continue
        ox = rng.randrange(0, WORLD_SIDE - box_w + 1)
        oy = rng.randrange(0, WORLD_SIDE - box_h + 1)
        local = grow_connected(rng, box_w, box_h)
        world_cells = {(ox + x, oy + y) for x, y in local}
        if _overlaps(world_cells, occupied, gap):
            continue
        # grow_connected already consumed rng, so build the city from that footprint
        # by calling the side/district path directly to avoid a second shape.
        return _city_from_local(
            rng,
            origin=(ox, oy),
            local=local,
            box_w=box_w,
            box_h=box_h,
            single_side=single_side,
            slavery=slavery,
            used_names=used_names,
            city_id=city_id,
        )
    return None


def _city_from_local(
    rng: random.Random,
    *,
    origin: tuple[int, int],
    local: set[tuple[int, int]],
    box_w: int,
    box_h: int,
    single_side: int | None,
    slavery: bool,
    used_names: set[str],
    city_id: str,
) -> dict[str, Any]:
    cx, cy = box_w // 2, box_h // 2
    if (cx, cy) not in local:
        local.add((cx, cy))
    sides = _internal_sides(local, box_w, box_h, single_side, rng)
    max_dist = max(max(abs(x - cx), abs(y - cy)) for x, y in local)
    peak = city_peak_density(len(local), max(sides.values()), rng)
    # Name after the band is known, so roll districts first.
    drafted: list[dict[str, Any]] = []
    for lx, ly in sorted(local):
        dist = max(abs(lx - cx), abs(ly - cy))
        density = cell_density(peak, dist, max_dist, rng)
        seed = rng.randrange(1, 2**31 - 1)
        side = sides[(lx, ly)]
        drafted.append(
            {
                "x": origin[0] + lx,
                "y": origin[1] + ly,
                "local": [lx, ly],
                "side": side,
                "density": density,
                "seed": seed,
                "districts": layout_districts(
                    rng, side=side, seed=seed, cell_density_value=density, slavery=slavery,
                ),
            }
        )
    population = population_of(drafted)
    band = population_band(population)
    xs = [cell["x"] for cell in drafted]
    ys = [cell["y"] for cell in drafted]
    center = next(cell for cell in drafted if cell["local"] == [cx, cy])
    return {
        "id": city_id,
        "name": _place_name(rng, band, used_names),
        "band": band,
        "population": population,
        "peak_density": peak,
        "x": center["x"],
        "y": center["y"],
        "span": [box_w, box_h],
        "bbox": [min(xs), min(ys), max(xs), max(ys)],
        "footprint": len(drafted),
        "fine_span": _fine_span(drafted),
        "cells": drafted,
    }


def index_cities(cities: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for city in cities:
        if not isinstance(city, dict):
            continue
        for cell in city.get("cells") or []:
            if not isinstance(cell, dict):
                continue
            index[f"{int(cell.get('x') or 0)},{int(cell.get('y') or 0)}"] = {"city": city, "cell": cell}
    return index


def _nearest_roads(cities: list[dict[str, Any]]) -> list[dict[str, int]]:
    roads: list[dict[str, int]] = []
    used: set[tuple[str, str]] = set()
    for city in cities:
        others = []
        for other in cities:
            if other["id"] == city["id"]:
                continue
            dist = max(abs(int(other["x"]) - int(city["x"])), abs(int(other["y"]) - int(city["y"])))
            if dist <= 240:
                others.append((dist, other))
        others.sort(key=lambda item: item[0])
        for _dist, other in others[:2]:
            pair = tuple(sorted((str(city["id"]), str(other["id"]))))
            if pair in used:
                continue
            used.add(pair)
            roads.append(
                {
                    "x1": int(city["x"]),
                    "y1": int(city["y"]),
                    "x2": int(other["x"]),
                    "y2": int(other["y"]),
                }
            )
    return roads


def _on_road(x: int, y: int, roads: list[dict[str, int]]) -> bool:
    for road in roads:
        x1, y1 = int(road["x1"]), int(road["y1"])
        x2, y2 = int(road["x2"]), int(road["y2"])
        if x < min(x1, x2) - 1 or x > max(x1, x2) + 1 or y < min(y1, y2) - 1 or y > max(y1, y2) + 1:
            continue
        dx, dy = x2 - x1, y2 - y1
        length2 = dx * dx + dy * dy
        if length2 <= 0:
            if x == x1 and y == y1:
                return True
            continue
        t = ((x - x1) * dx + (y - y1) * dy) / length2
        if t < 0 or t > 1:
            continue
        if max(abs(x - (x1 + t * dx)), abs(y - (y1 + t * dy))) <= 0.55:
            return True
    return False


def value_noise(seed: int, x: int, y: int, scale: int = 9) -> float:
    scale = max(2, int(scale))
    x0, y0 = x // scale, y // scale
    fx = (x % scale) / scale
    fy = (y % scale) / scale
    sx = fx * fx * (3 - 2 * fx)
    sy = fy * fy * (3 - 2 * fy)

    def corner(ix: int, iy: int) -> float:
        return mix_hash(seed, ix, iy) / 0xFFFFFFFF

    v00 = corner(x0, y0)
    v10 = corner(x0 + 1, y0)
    v01 = corner(x0, y0 + 1)
    v11 = corner(x0 + 1, y0 + 1)
    return v00 * (1 - sx) * (1 - sy) + v10 * sx * (1 - sy) + v01 * (1 - sx) * sy + v11 * sx * sy


# One noise field, six roles. Each preset names the tile that fills a role,
# so a cavern world is not a forest with the label changed.
_PRESET_BANDS: dict[str, dict[str, Any]] = {
    "deep_caverns": {
        "sink": "water", "sink_at": 0.12,
        "wall": "cliff", "wall_at": 0.90,
        "rise": "crystal", "rise_at": 0.78,
        "damp": "mushroom", "damp_at": 0.72,
        "dry": "lava", "dry_at": 0.10,
        "ground": "cavern",
    },
    "forest_march": {
        "sink": "water", "sink_at": 0.14,
        "wall": "mountain", "wall_at": 0.90,
        "rise": "hill", "rise_at": 0.78,
        "damp": "forest", "damp_at": 0.36,
        "dry": "plains", "dry_at": 0.16,
        "ground": "forest",
    },
    "coastal_scrap": {
        "sink": "water", "sink_at": 0.40,
        "wall": "cliff", "wall_at": 0.90,
        "rise": "beach", "rise_at": 0.72,
        "damp": "ruins", "damp_at": 0.78,
        "dry": "plains", "dry_at": 0.0,
        "ground": "plains",
    },
    "ash_plain": {
        "sink": "ash", "sink_at": 0.16,
        "wall": "mountain", "wall_at": 0.84,
        "rise": "hill", "rise_at": 0.74,
        "damp": "ruins", "damp_at": 0.80,
        "dry": "ash", "dry_at": 0.35,
        "ground": "plains",
    },
    "mountain_pass": {
        "sink": "water", "sink_at": 0.08,
        "wall": "mountain", "wall_at": 0.58,
        "rise": "cliff", "rise_at": 0.46,
        "damp": "forest", "damp_at": 0.82,
        "dry": "ice", "dry_at": 0.28,
        "ground": "hill",
    },
    "orbital_belt": {
        "sink": "void", "sink_at": 0.0,
        "wall": "asteroid", "wall_at": 0.88,
        "rise": "asteroid", "rise_at": 0.80,
        "damp": "nebula", "damp_at": 0.72,
        "dry": "void", "dry_at": 0.55,
        "ground": "void",
    },
    "star_lane": {
        "sink": "void", "sink_at": 0.0,
        "wall": "asteroid", "wall_at": 0.94,
        "rise": "nebula", "rise_at": 0.86,
        "damp": "nebula", "damp_at": 0.90,
        "dry": "void", "dry_at": 0.0,
        "ground": "void",
    },
    "frontier_any": {
        "sink": "water", "sink_at": 0.20,
        "wall": "mountain", "wall_at": 0.86,
        "rise": "hill", "rise_at": 0.74,
        "damp": "forest", "damp_at": 0.70,
        "dry": "desert", "dry_at": 0.20,
        "ground": "plains",
    },
}

_PRESET_MATERIALS: dict[str, tuple[str, ...]] = {
    "deep_caverns": ("wet limestone", "glow-fungus", "raw crystal", "basalt", "black water"),
    "forest_march": ("oak", "loam", "river stone", "thatch", "ironwood"),
    "coastal_scrap": ("salt timber", "rusted plate", "sand", "tar", "barnacle stone"),
    "ash_plain": ("ash", "cinder", "obsidian", "scrap iron", "dried clay"),
    "mountain_pass": ("granite", "ice", "pine", "slate", "wool"),
    "orbital_belt": ("hull alloy", "regolith", "vacuum glass", "sealant", "ice"),
    "star_lane": ("star-metal", "nebula dust", "hull ceramic", "cold iron"),
    "frontier_any": ("mixed timber", "local stone", "road dust", "trade cloth"),
}

_PRESET_ART: dict[str, str] = {
    "deep_caverns": "underground cavern tile, damp stone, bioluminescent fungus, no sky and no trees",
    "forest_march": "temperate forest floor tile, oak shade, moss and loam",
    "coastal_scrap": "industrial coast tile, salt, rust, sand and scrap",
    "ash_plain": "ash waste tile, cinders and dead ground, no green canopy",
    "mountain_pass": "high alpine tile, granite, ice and sparse pine",
    "orbital_belt": "airless orbital tile, rock, hull metal and starfield",
    "star_lane": "deep-space tile, black vacuum and faint nebula",
    "frontier_any": "mixed frontier tile, road dust and whatever ground is local",
}

# A kind is a leaning. "Dwarven" may be dwarves or a people near that idea.
_KINDS: dict[str, dict[str, Any]] = {
    "human": {
        "leaning": "human",
        "says": "humans, or a people who would pass for human",
        "terrains": frozenset({"plains", "road", "town", "city", "village", "farm", "beach", "ash", "ruins", "forest"}),
    },
    "elven": {
        "leaning": "elven",
        "says": "elves, or a people near that idea who are not necessarily elves",
        "terrains": frozenset({"forest", "hill"}),
    },
    "dwarven": {
        "leaning": "dwarven",
        "says": "dwarves, or a stone-living people near that idea",
        "terrains": frozenset({"mountain", "hill", "cliff", "cavern", "crystal", "dungeon", "road"}),
    },
    "smallfolk": {
        "leaning": "smallfolk",
        "says": "halflings, or a smaller people near that idea",
        "terrains": frozenset({"plains", "farm", "village"}),
    },
    "orcish": {
        "leaning": "orcish",
        "says": "orcs, or a hardy people near that idea",
        "terrains": frozenset({"ash", "ruins", "cliff", "lava", "mountain"}),
    },
    "scaled": {
        "leaning": "scaled",
        "says": "a scaled people, or something near that, not one fixed species",
        "terrains": frozenset({"water", "swamp", "lava", "beach"}),
    },
    "deep": {
        "leaning": "deep-elven",
        "says": "a deep-elven people, or something only near elves of the dark",
        "terrains": frozenset({"cavern", "mushroom", "crystal", "dungeon"}),
    },
    "darkling": {
        "leaning": "darkling",
        "says": "creatures that lurk in the dark, or a people near that idea, not one fixed monster",
        "terrains": frozenset({"cavern", "mushroom", "dungeon", "ruins", "water", "lava"}),
    },
    "spacer": {
        "leaning": "spacer",
        "says": "people built for ships and vacuum, often human, or a people near that",
        "terrains": frozenset({"void", "asteroid", "nebula", "station", "colony"}),
    },
}

_PRESET_PEOPLE: dict[str, dict[str, Any]] = {
    "deep_caverns": {
        "majority": ("dwarven", "darkling"),
        "minority": ("deep", "scaled", "human"),
        "majority_share": 0.82,
        "says": (
            "When this land is lived in, most inhabitants are creatures that lurk in the dark, "
            "and dwarves or a stone-living people near that idea. Other peoples are uncommon."
        ),
    },
    "forest_march": {
        "majority": ("human",),
        "minority": ("elven", "smallfolk", "dwarven"),
        "majority_share": 0.72,
        "says": "When this land is lived in, most inhabitants are human or a people who would pass for human. Elves, smaller folk, and stone-folk turn up, especially off the roads.",
    },
    "coastal_scrap": {
        "majority": ("human",),
        "minority": ("dwarven", "scaled"),
        "majority_share": 0.78,
        "says": "When this land is lived in, most inhabitants are human. Stone-folk and scaled people are the uncommon ones.",
    },
    "ash_plain": {
        "majority": ("human",),
        "minority": ("orcish",),
        "majority_share": 0.7,
        "says": "When this land is lived in, most inhabitants are human remnants. A hardy people near the orcish idea is uncommon.",
    },
    "mountain_pass": {
        "majority": ("dwarven",),
        "minority": ("human", "elven"),
        "majority_share": 0.74,
        "says": "When this land is lived in, most inhabitants are dwarves or a stone-living people near that idea. Humans and elves are uncommon.",
    },
    "orbital_belt": {
        "majority": ("spacer",),
        "minority": ("human",),
        "majority_share": 0.8,
        "says": "When this belt is lived in, most inhabitants are people built for ships and vacuum. Unadapted humans are uncommon.",
    },
    "star_lane": {
        "majority": ("spacer",),
        "minority": ("human",),
        "majority_share": 0.84,
        "says": "When this lane is lived in, most inhabitants are people built for ships and vacuum.",
    },
    "frontier_any": {
        "majority": ("human",),
        "minority": ("elven", "dwarven", "orcish", "smallfolk"),
        "majority_share": 0.62,
        "says": "When this land is lived in, humans are the largest share. Other peoples are ordinary chances, not visitors from nowhere.",
    },
}

PROVINCE = 48


def bands_for_preset(preset_id: str) -> dict[str, Any]:
    raw = _PRESET_BANDS.get(str(preset_id or ""))
    return dict(raw) if raw else {}


def bands_for_world(world: dict[str, Any]) -> dict[str, Any]:
    stored = world.get("terrain_bands")
    if isinstance(stored, dict) and stored.get("ground"):
        return stored
    return bands_for_preset(str(world.get("preset_id") or ""))


def materials_for(preset_id: str) -> list[str]:
    return list(_PRESET_MATERIALS.get(str(preset_id or ""), ()))


def art_look_for(preset_id: str) -> str:
    return str(_PRESET_ART.get(str(preset_id or ""), ""))


def people_profile_for(preset_id: str) -> dict[str, Any]:
    raw = _PRESET_PEOPLE.get(str(preset_id or ""))
    if not raw:
        return {}
    return {
        "majority": list(raw["majority"]),
        "minority": list(raw["minority"]),
        "majority_share": float(raw["majority_share"]),
        "says": str(raw["says"]),
    }


def terrain_from_bands(bands: dict[str, Any], seed: int, x: int, y: int) -> str:
    height = value_noise(seed, x, y, 9)
    moist = value_noise(seed + 17, x, y, 13)
    if height < float(bands.get("sink_at") or 0):
        return str(bands.get("sink") or "water")
    if height > float(bands.get("wall_at") or 1):
        return str(bands.get("wall") or "mountain")
    if height > float(bands.get("rise_at") or 1):
        return str(bands.get("rise") or "hill")
    if moist > float(bands.get("damp_at") or 1):
        return str(bands.get("damp") or "forest")
    if moist < float(bands.get("dry_at") or 0):
        return str(bands.get("dry") or "plains")
    return str(bands.get("ground") or "plains")


def _terrain_salt(terrain: str) -> int:
    total = 0
    for ch in str(terrain or ""):
        total = (total + ord(ch) * 17) & 0xFFFF
    return total or 1


def _kind_weight(kind_id: str, terrain: str, majority: bool) -> int:
    spec = _KINDS.get(kind_id) or {}
    terrains = spec.get("terrains") or frozenset()
    return (6 if majority else 1) + (4 if terrain in terrains else 0)


def _pick_kind(pool: list[tuple[str, bool]], terrain: str, roll: int) -> str:
    weights = [(kind_id, _kind_weight(kind_id, terrain, majority)) for kind_id, majority in pool]
    total = sum(weight for _, weight in weights) or 1
    cursor = int(roll) % total
    for kind_id, weight in weights:
        if cursor < weight:
            return kind_id
        cursor -= weight
    return pool[0][0]


def people_leaning(world: dict[str, Any], x: int, y: int, terrain: str | None = None) -> dict[str, Any]:
    """Who might live on this stretch. Empty means the stretch can be empty.

    The same ground inside one province shares a kind. A kind is not a census:
    the model may use it, skip it, or treat it as a people near the idea.
    """
    profile = world.get("people_profile")
    if not isinstance(profile, dict) or not profile.get("majority"):
        profile = people_profile_for(str(world.get("preset_id") or ""))
    if not profile:
        return {}
    seed = int(world.get("seed") or 1)
    if terrain is None:
        bands = bands_for_world(world)
        if bands:
            terrain = terrain_from_bands(bands, seed, int(x), int(y))
        else:
            terrain = terrain_state(str(world.get("theme") or "mixed"), seed, int(x), int(y))
    terrain = str(terrain or "")
    density = int(world.get("density_percent") or 20)
    px, py = int(x) // PROVINCE, int(y) // PROVINCE
    salt = _terrain_salt(terrain)
    chance = max(0.08, min(0.82, 0.08 + 0.9 * (max(0, min(100, density)) / 100)))
    majority = [str(item) for item in profile.get("majority") or []]
    result = {
        "majority": majority,
        "majority_says": str(profile.get("says") or ""),
        "province": [px, py],
        "kind": "",
        "option": (
            "This stretch has no local people-kind. It may be empty. "
            "If someone must live here, they are usually the world's majority, and they may still be absent."
        ),
    }
    unit = mix_hash(seed, px, py, 70 + salt) / 0xFFFFFFFF
    if unit > chance:
        return result
    share = float(profile.get("majority_share") or 0.75)
    gate = mix_hash(seed, px, py, 80 + salt) / 0xFFFFFFFF
    minority = [str(item) for item in profile.get("minority") or []]
    if gate <= share or not minority:
        pool = [(kind_id, True) for kind_id in majority]
    else:
        pool = [(kind_id, False) for kind_id in minority]
    pool = [(kind_id, flag) for kind_id, flag in pool if kind_id in _KINDS]
    if not pool:
        return result
    kind_id = _pick_kind(pool, terrain, mix_hash(seed, px, py, 90 + salt))
    spec = _KINDS[kind_id]
    result["kind"] = str(spec["leaning"])
    result["option"] = (
        f"If this stretch needs inhabitants, they may be {spec['says']}. "
        "They may also be absent. The word is a leaning, not a census and not a name that must be spoken."
    )
    return result


def terrain_state(theme: str, seed: int, x: int, y: int) -> str:
    height = value_noise(seed, x, y, 9)
    moist = value_noise(seed + 17, x, y, 13)
    if theme == "post_collapse":
        if height > 0.84:
            return "mountain"
        if height > 0.74:
            return "hill"
        if height < 0.16:
            return "ash"
        if moist > 0.8:
            return "ruins"
        return "ash" if moist < 0.35 else "plains"
    if theme in {"space_opera", "far_future"}:
        if height < 0.18:
            return "void"
        if height > 0.86:
            return "asteroid"
        return "plains"
    if height < 0.2:
        return "water"
    if height > 0.86:
        return "mountain"
    if height > 0.74:
        return "hill"
    if moist > 0.7:
        return "forest"
    if moist < 0.2:
        return "desert"
    return "plains"


def world_cell(world: dict[str, Any], x: int, y: int) -> dict[str, Any] | None:
    width = int(world.get("width") or WORLD_SIDE)
    height = int(world.get("height") or WORLD_SIDE)
    if not (0 <= x < width and 0 <= y < height):
        return None
    index = world.get("cell_index")
    if not isinstance(index, dict):
        index = index_cities(world.get("cities") or [])
        world["cell_index"] = index
    found = index.get(f"{x},{y}")
    if isinstance(found, dict):
        city = found.get("city") or {}
        cell = found.get("cell") or {}
        band = str(city.get("band") or "village")
        state = _world_state_for_band(band)
        return {
            "x": x,
            "y": y,
            "state": state,
            "walkable": True,
            "elevation": 0,
            "city_id": city.get("id") or "",
            "name": city.get("name") or "",
            "density": cell.get("density"),
            "side": cell.get("side"),
            "image_path": "",
            "image_data_url": "",
        }
    if _on_road(x, y, world.get("roads") or []):
        state = "road"
    else:
        bands = bands_for_world(world)
        seed = int(world.get("seed") or 1)
        if bands:
            state = terrain_from_bands(bands, seed, x, y)
        else:
            state = terrain_state(str(world.get("theme") or "mixed"), seed, x, y)
    return {
        "x": x,
        "y": y,
        "state": state,
        "walkable": state not in _BLOCKED,
        "elevation": 1 if state in {"mountain", "hill", "cliff"} else 0,
        "image_path": "",
        "image_data_url": "",
    }


def _settlement_row(city: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": city.get("id"),
        "x": city.get("x"),
        "y": city.get("y"),
        "state": _world_state_for_band(str(city.get("band") or "")),
        "name": city.get("name"),
        "tile_count": city.get("footprint"),
        "population_band": city.get("band"),
        "population": city.get("population"),
        "bbox": city.get("bbox"),
        "summary": (
            f"{city.get('name')} · {city.get('band')} · {city.get('population')} people · "
            f"span {city.get('span', ['?', '?'])[0]}×{city.get('span', ['?', '?'])[1]} world cells"
        ),
    }


def build_world(
    preset: dict[str, Any] | None,
    seed: int,
    density_percent: int | None = None,
    notice_percent: int | None = None,
) -> dict[str, Any]:
    rng = random.Random(int(seed))
    theme = theme_key(preset)
    if density_percent is None:
        density = advise_density_percent(theme, rng)
        source = "theme"
    else:
        density = normalize_density(density_percent)
        source = "given"
    plan = plan_city_scale(density, theme, rng)
    slavery = theme_allows_slavery(theme)
    cities: list[dict[str, Any]] = []
    occupied: set[tuple[int, int]] = set()
    used_names: set[str] = set()
    serial = 1
    for _ in range(int(plan["large_city_count"])):
        city = _stamp_city(
            rng,
            occupied=occupied,
            large=True,
            plan=plan,
            slavery=slavery,
            used_names=used_names,
            city_id=f"C{serial}",
            gap=24,
        )
        serial += 1
        if city:
            cities.append(city)
            occupied.update((int(cell["x"]), int(cell["y"])) for cell in city["cells"])
    for _ in range(int(plan["settlement_count"])):
        city = _stamp_city(
            rng,
            occupied=occupied,
            large=False,
            plan=plan,
            slavery=slavery,
            used_names=used_names,
            city_id=f"C{serial}",
            gap=8,
        )
        serial += 1
        if city:
            cities.append(city)
            occupied.update((int(cell["x"]), int(cell["y"])) for cell in city["cells"])
    # After the cities: this draw must not move a street or a name already chosen.
    from app.local_intel import apply_notice_plan

    notice_value, notice_source = apply_notice_plan(cities, theme, rng, notice_percent)
    if cities:
        ranked = sorted(cities, key=lambda item: int(item.get("population") or 0))
        start_city = ranked[len(ranked) // 2]
        px, py = int(start_city["x"]), int(start_city["y"])
    else:
        px = py = WORLD_SIDE // 2
    world = {
        "scale": "world",
        "width": WORLD_SIDE,
        "height": WORLD_SIDE,
        "seed": int(seed),
        "preset_id": str((preset or {}).get("id") or ""),
        "age": str((preset or {}).get("age") or ""),
        "environment": str((preset or {}).get("environment") or ""),
        "theme": theme,
        "terrain_bands": bands_for_preset(str((preset or {}).get("id") or "")),
        "materials": materials_for(str((preset or {}).get("id") or "")),
        "people_profile": people_profile_for(str((preset or {}).get("id") or "")),
        "density_percent": density,
        "density_source": source,
        "scale_plan": plan,
        "allows_slavery": slavery,
        "notice_percent": notice_value,
        "notice_source": notice_source,
        "revealed": [],
        "cities": cities,
        "roads": _nearest_roads(cities),
        "settlements_meta": [_settlement_row(city) for city in cities],
        "player": {"x": px, "y": py},
        "visited": [f"{px},{py}"],
        "landmarks": [],
        "hidden_bases": [],
        "place_anchors": {},
        "knowledge": {"settlements": [], "danger": [], "notes": [], "sources": []},
        "stats": {
            "world_side": WORLD_SIDE,
            "density_percent": density,
            "density_source": source,
            "city_count": len(cities),
            "large_city_count": int(plan["large_city_count"]),
            "max_footprint": max((int(city["footprint"]) for city in cities), default=0),
            "max_fine_span": max((int(city["fine_span"]) for city in cities), default=0),
        },
    }
    world["cell_index"] = index_cities(cities)
    return world


def preview_window(world: dict[str, Any], radius: int = 24) -> dict[str, Any]:
    """A small window around the player for the setup canvas. Not the whole world."""
    radius = clamp_int(radius, 4, 32)
    px = int((world.get("player") or {}).get("x") or 0)
    py = int((world.get("player") or {}).get("y") or 0)
    width = int(world.get("width") or WORLD_SIDE)
    height = int(world.get("height") or WORLD_SIDE)
    x0 = clamp_int(px - radius, 0, max(0, width - 1))
    y0 = clamp_int(py - radius, 0, max(0, height - 1))
    x1 = min(width - 1, x0 + radius * 2)
    y1 = min(height - 1, y0 + radius * 2)
    tiles = []
    glyphs = {
        "water": "~", "plains": ".", "forest": "T", "mountain": "^", "hill": "n",
        "city": "#", "town": "o", "village": "v", "road": "-", "ash": ",", "ruins": "x",
        "desert": ":", "void": " ", "asteroid": "*", "cavern": "c", "mushroom": "m",
        "crystal": "y", "lava": "=", "cliff": "|", "ice": "+", "nebula": "%",
        "beach": "b", "dungeon": "D",
    }
    lines = []
    for y in range(y0, y1 + 1):
        chars = []
        for x in range(x0, x1 + 1):
            cell = world_cell(world, x, y) or {"state": "?"}
            local_x = x - x0
            local_y = y - y0
            tiles.append(
                {
                    "x": local_x,
                    "y": local_y,
                    "world_x": x,
                    "world_y": y,
                    "state": cell.get("state"),
                    "walkable": cell.get("walkable", True),
                    "name": cell.get("name") or "",
                }
            )
            if x == px and y == py:
                chars.append("@")
            else:
                chars.append(glyphs.get(str(cell.get("state") or ""), "?"))
        lines.append("".join(chars))
    return {
        "width": x1 - x0 + 1,
        "height": y1 - y0 + 1,
        "origin_x": x0,
        "origin_y": y0,
        "player": {"x": px - x0, "y": py - y0},
        "tiles": tiles,
        "ascii": "\n".join(lines),
    }
