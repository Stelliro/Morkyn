"""Where-questions about wild places, answered from the land around the player.

Status: built, not wired (TODO n22). This is the "hunting grounds get no engine answer" gap of that item.

parse_wild_question() recognises an ask ("where", "is there a", "know of", "nearest", "which way") about one
of the FEATURES (hunting grounds, ford, cave, ruin, standing stones, fresh water, high ground, woods, marsh,
road, hidden camp). scan() reads the tiles within WILD_HORIZON cells of the player (board grid cells, or
world_scale.world_cell samples on a world chart) plus landmarks, hidden_bases and lived knowledge, and
resolve_wild_question() turns the nearest match into the local_intel DirectionHint shape: told or not by
local_intel.will_tell (public news for every feature; an undiscovered camp is forbidden news), the told cell
blurred past 4 cells by local_intel.blur_cell, a compass word and one sentence of wording. Pure: nothing here
writes the map, the journal or settings (on a world chart the first cell sample caches chart["cell_index"],
as world_scale.world_cell does for every reader; nothing else on the chart is touched). No tables and no
settings rows: ensure_schema() is a documented no-op. World charts have no landmarks or hidden bases, so
caves, ruins, stones and camps are answered there only when a knowledge marker exists. The live game does
not call this module.

Wiring (not done):
  app/local_intel.py:turn_direction_hint() (line 1317) -> its first statement returns None when
      parse_direction_question(player_input) is None. Make that `asked = parse_direction_question(player_input)`
      and return None only when asked is None and not wild_places.is_wild_question(player_input). Then, after
      chart, speaker and day are built, the last line becomes
      `return resolve_direction(chart, player_input, speaker, day=day, gold=_player_gold(conn)) if asked is not
      None else wild_places.resolve_wild_question(chart, player_input, speaker, day=day, gold=_player_gold(conn))`.
      prompt_direction_hint and apply_hint_to_map then work unchanged.
  app/local_intel.py:apply_turn_intel() (line 1389) unresolved branch -> chart, speaker and gold are built
      inside `if asked is not None and not faction_held`; hoist that block out so it also runs when asked is
      None and wild_places.is_wild_question(player_input), and in that case call the same
      resolve_wild_question (day=_world_day(conn)) before _record_hint.
  app/local_intel.py:_record_hint() (line 1446) -> lift the `scale != "world"` early return for hints whose
      place["kind"] == "wild" (apply_hint_to_map already works on boards); town_moves.record_told returns ""
      for a wild place and needs no change. turn_direction_hint and apply_turn_intel keep their own
      `scale != "world"` early returns (lines 1333 and 1413), so board answers need those lifted as well.
  app/turn_prompts.py:gate_after_turn() (line 524) direction_hint branch -> when
      (hint.get("place") or {}).get("kind") == "wild", candidates.append(wild_places.travel_candidate(hint))
      in place of the inline tuple. The inline rule builds a blurred or forbidden label from hint["good"],
      which for a wild hint is the FEATURES key ("where you were pointed for hunting_grounds, north");
      travel_candidate reads the spoken label and carries the feature key in source["feature"].

Turn on:
  [ ] no playthrough_options flag: a gap fix that turns on with its hook lines
  [ ] the two local_intel calls, the _record_hint guard and the gate_after_turn candidate line
  [ ] no schema, no settings, no route, no UI
  [ ] prompt: none (the hint rides the existing direction_hint line)

Tests: tests/test_wild_places.py
"""
from __future__ import annotations

import re
from typing import Any, Iterable

from app.local_intel import (
    BRIBE_GOLD,
    blur_cell,
    compass_word,
    direction_roll,
    prompt_direction_hint,
    stand_in_check,
    will_tell,
)
from app.tile_world import (
    NEIGHBOR_ORDER,
    SETTLEMENT_STATES,
    _DIRECTIONS,
    _cell_at,
    _player_xy,
    _rebuild_grid,
    tile_walkable,
)

# ---------------------------------------------------------------------------
# Rules tables (data)
# ---------------------------------------------------------------------------

WILD_HORIZON = 12  # cells scanned around the player (Chebyshev): about three hours on foot
HORIZON_MIN, HORIZON_MAX = 1, 24  # scan() clamps a caller's horizon to this range
EXACT_WITHIN = 4  # the cell is named exactly within this many cells (blur_cell's rule)
MIN_WOOD_NEIGHBOURS = 2  # hunting grounds: a wood tile with this many wood neighbours

# local_intel._ASKS_WAY_RE plus the wild-place asks n22 names.
ASKS_RE = re.compile(
    r"\b(?:where|closest|nearest|directions?|which\s+way|point\s+me|show\s+me\s+the\s+way|"
    r"how\s+(?:do|can|would|should)\s+(?:i|we|one)\s+(?:get|find|reach)|know\s+(?:of|where|any)|looking\s+for|"
    r"is\s+there\s+(?:a|an|any|some)|any\s+\w+\s+(?:near|nearby|around|close))\b"
)
# A copy of local_intel._BRIBE_RE (private there).
BRIBE_RE = re.compile(
    r"\b(bribe|slip\s+(?:him|her|them)|pay for the information|offer(?:s|ed|ing)? coin|hand(?:s|ed|ing)? over coin)\b",
    re.IGNORECASE,
)
CLOSEST_RE = re.compile(r"\b(closest|nearest)\b")

# Ordered: the first feature whose words match wins ("hunt in the forest" is hunting_grounds, not woods).
# rule: how a cell qualifies; states / landmarks: tile states and landmark states that count; public: told as
# public news (will_tell forbidden=False); False means forbidden news unless the candidate is discovered.
FEATURES: tuple[tuple[str, dict[str, Any]], ...] = (
    ("hunting_grounds", {"words": r"\b(hunt\w*|game trail|deer|boar|hares?|rabbits?|quarry)\b",
                         "label": "hunting grounds", "noun": "good hunting", "rule": "wood_edge",
                         "states": ("forest", "mushroom"), "landmarks": (), "public": True}),
    ("ford",            {"words": r"\b(fords?|crossing|cross\s+the\s+(?:river|water|stream)|shallows|bridge)\b",
                         "label": "a ford", "noun": "a ford", "rule": "water_crossing",
                         "states": ("bridge",), "landmarks": (), "public": True}),
    ("cave",            {"words": r"\b(caves?|cavern\w*|grotto|hollow|dens?|dungeon|tunnels?)\b",
                         "label": "a cave", "noun": "a cave", "rule": "state",
                         "states": ("cavern", "dungeon"), "landmarks": ("dungeon", "cavern"), "public": True}),
    ("ruin",            {"words": r"\b(ruins?|old\s+(?:fort|tower|keep|walls?)|wreck|derelict)\b",
                         "label": "ruins", "noun": "the ruins", "rule": "state",
                         "states": ("ruins", "wreck"), "landmarks": ("ruins", "wreck"), "public": True}),
    ("stones",          {"words": r"\b(standing\s+stones?|monolith|old\s+stones?|crystals?|shrine|anomaly)\b",
                         "label": "the old stones", "noun": "the old stones", "rule": "state",
                         "states": ("monolith", "crystal", "anomaly"), "landmarks": ("monolith", "crystal", "anomaly"),
                         "public": True}),
    ("spring",          {"words": r"\b(springs?|fresh\s+water|drinking\s+water|stream|brook|river|lake|waterfall|water)\b",
                         "label": "fresh water", "noun": "fresh water", "rule": "shore",
                         "states": ("waterfall",), "landmarks": ("waterfall",), "public": True}),
    ("high_ground",     {"words": r"\b(hills?|high\s+ground|lookout|vantage|ridge|overlook|mesa)\b",
                         "label": "high ground", "noun": "high ground", "rule": "state",
                         "states": ("hill", "mesa"), "landmarks": (), "public": True}),
    ("woods",           {"words": r"\b(woods?|forest|trees|timber|firewood)\b",
                         "label": "the woods", "noun": "the woods", "rule": "state",
                         "states": ("forest", "mushroom"), "landmarks": (), "public": True}),
    ("marsh",           {"words": r"\b(marsh|swamp|bog|fen|reeds)\b",
                         "label": "the marsh", "noun": "the marsh", "rule": "state",
                         "states": ("swamp",), "landmarks": (), "public": True}),
    ("road",            {"words": r"\b(roads?|highway|track|trail|path)\b",
                         "label": "the road", "noun": "the road", "rule": "state",
                         "states": ("road", "bridge"), "landmarks": (), "public": True}),
    # The bare word "camp" is left out on purpose: it also means the player's own camp.
    ("hidden_camp",     {"words": r"\b(bandits?|bandit\s+camp|hideout|hidden\s+(?:camp|base)|lair|outlaws?|smugglers?)\b",
                         "label": "the camp", "noun": "the camp", "rule": "hidden_base",
                         "states": (), "landmarks": ("hidden_base",), "public": False}),
)
_FEATURE_INDEX: dict[str, dict[str, Any]] = {key: spec for key, spec in FEATURES}
_FEATURE_WORDS: dict[str, re.Pattern[str]] = {key: re.compile(spec["words"]) for key, spec in FEATURES}

# Cell rules (all read through tile_world._cell_at, so boards and world charts behave alike):
#  state           cell.state in states (walkable or not: ruins and dungeon are walkable, waterfall is a landmark tile)
#  wood_edge       state in states AND >= MIN_WOOD_NEIGHBOURS of the 8 neighbours share it AND >= 1 neighbour is walkable
#                  with a different state (the edge game feeds on). score = same-state neighbours (2..8)
#  water_crossing  a "bridge" cell (score 3); or a "water" cell W with walkable land on both sides along one axis,
#                  W-d and W+d for d in ((1,0),(0,1)) (a one-cell-wide run); the candidate cell is the land cell on the
#                  player's side so Travel there can reach it (score 2)
#  shore           a waterfall tile/landmark (score 3); else a walkable non-settlement cell with a "water" neighbour
#                  (score 1); the candidate is the walkable cell
#  hidden_base     hidden_bases rows (discovered -> public candidate named "Bandit camp"/"Hidden camp"; undiscovered ->
#                  candidate with discovered False, answered only through will_tell's forbidden branch and always blurred),
#                  landmarks with kind "hidden_base", and knowledge.danger rows whose id starts "lived-" (label kept as
#                  the candidate name, discovered True, source "knowledge")
# Settlement cells never qualify as a candidate for the state, wood_edge or shore rules; water_crossing counts
# them only as the "land" on either side of a run. A settlement cell is one
# stamped with a settlement_id (board blob) or city_id (world city), or whose state is a settlement word; the
# landmark words ruins, dungeon and gate sit in tile_world.SETTLEMENT_STATES as map states, not settlements
# (contracts 1.8), so they stay open to the state rule.
SCORE_BRIDGE, SCORE_FORD, SCORE_WATERFALL, SCORE_SHORE, SCORE_STATE, SCORE_CAMP = 3, 2, 3, 1, 1, 1
WATER_STATE = "water"
BRIDGE_STATE = "bridge"
WATERFALL_STATE = "waterfall"
CROSSING_AXES: tuple[tuple[int, int], ...] = ((1, 0), (0, 1))
SETTLEMENT_CELL_STATES: frozenset[str] = frozenset(SETTLEMENT_STATES) - frozenset({"ruins", "dungeon", "gate"})
HIDDEN_CAMP_NAMES = {"bandit": "Bandit camp"}  # any other owner: HIDDEN_CAMP_DEFAULT_NAME (tile_world wording)
HIDDEN_CAMP_DEFAULT_NAME = "Hidden camp"
LIVED_KNOWLEDGE_PREFIX = "lived-"

# Choosing: nearest Chebyshev distance to the player; ties -> higher score -> clockwise bearing from north
# (tile_world.NEIGHBOR_ORDER) -> smaller (x, y). Candidates beyond WILD_HORIZON are not scanned at all.
# specificity "area": the same pick (the land has no districts); kept in the hint for the prompt.
_BEARING_INDEX: dict[str, int] = {name: i for i, (name, _dx, _dy) in enumerate(NEIGHBOR_ORDER)}

DISTANCE_WORDS: tuple[tuple[int, str], ...] = (
    (2, "just over there"), (4, "close by"), (8, "an hour or two out"), (WILD_HORIZON, "half a day out"),
)

# {Noun} from FEATURES (capitalised), {compass}, {dist} from DISTANCE_WORDS, {name} the landmark name when it has one
WORDING: dict[str, str] = {
    "exact":          "{Noun} lies {compass} of here, {dist}.",  # "The road lies east of here, close by."
    "exact_here":     "{Noun} is right here.",
    "blurred":        "{Noun} is {compass} of here, {dist}. Keep going that way past where the map shows.",
    "named":          "{name} is {compass} of here, {dist}.",  # exact and the landmark carries a name
    "forbidden":      "Keep that to yourself: something {compass} of here, {dist}, that does not want finding.",
    "forbidden_here": "Keep that to yourself: something right here does not want finding.",  # standing on it
    "none":           "",  # told False
}

PLACE_KIND = "wild"
TRAVEL_SOURCE_KIND = "direction_hint"


# ---------------------------------------------------------------------------
# Schema (none)
# ---------------------------------------------------------------------------


def ensure_schema(conn) -> None:
    """No tables and no settings rows: nothing to create. Kept so a wiring pass can call every module alike."""
    del conn
    return None


# ---------------------------------------------------------------------------
# The ask
# ---------------------------------------------------------------------------


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").lower()).strip()


def feature(key: str) -> dict[str, Any]:
    """The FEATURES entry for ``key``. KeyError on an unknown key."""
    return _FEATURE_INDEX[str(key)]


def features_in_text(text: str) -> list[str]:
    """Every feature whose words match, in FEATURES order."""
    low = _norm(text)
    if not low:
        return []
    return [key for key, _spec in FEATURES if _FEATURE_WORDS[key].search(low)]


def parse_wild_question(text: str) -> dict[str, Any] | None:
    """The WildAsk, or None unless the line asks the way and names a wild feature."""
    low = _norm(text)
    if not low or not ASKS_RE.search(low):
        return None
    found = features_in_text(low)
    if not found:
        return None
    return {
        "feature": found[0],
        "specificity": "closest" if CLOSEST_RE.search(low) else "area",
        "bribe": bool(BRIBE_RE.search(low)),
        "text": low,
    }


def is_wild_question(text: str) -> bool:
    return parse_wild_question(text) is not None


# ---------------------------------------------------------------------------
# Reading the land
# ---------------------------------------------------------------------------


def _state_of(cell: dict[str, Any] | None) -> str:
    return str((cell or {}).get("state") or "")


def _is_settlement_cell(cell: dict[str, Any] | None) -> bool:
    if not isinstance(cell, dict):
        return False
    if cell.get("settlement_id") or cell.get("city_id"):
        return True
    return _state_of(cell) in SETTLEMENT_CELL_STATES


def _grid_for(chart: dict[str, Any]) -> list[list[dict[str, Any]]] | None:
    """The board grid, or None on a world chart (where _cell_at samples the seed)."""
    if str(chart.get("scale") or "") == "world":
        return None
    return _rebuild_grid(chart)


def _cell(chart: dict[str, Any], x: int, y: int, grid) -> dict[str, Any] | None:
    try:
        return _cell_at(chart, int(x), int(y), grid)
    except (TypeError, ValueError, KeyError, IndexError):
        return None


def _neighbours(chart: dict[str, Any], x: int, y: int, grid) -> list[dict[str, Any]]:
    cells = []
    for dx, dy in _DIRECTIONS.values():
        cell = _cell(chart, x + dx, y + dy, grid)
        if isinstance(cell, dict):
            cells.append(cell)
    return cells


def _wood_edge_score(chart: dict[str, Any], x: int, y: int, states: tuple[str, ...], grid) -> int:
    """Same-state neighbours when the cell is a wood edge, else 0."""
    cell = _cell(chart, x, y, grid)
    if not isinstance(cell, dict) or _is_settlement_cell(cell):
        return 0
    state = _state_of(cell)
    if state not in states:
        return 0
    same = 0
    open_edge = False
    for other in _neighbours(chart, x, y, grid):
        other_state = _state_of(other)
        if other_state == state:
            same += 1
        elif tile_walkable(other) and not _is_settlement_cell(other):
            open_edge = True
    if same >= MIN_WOOD_NEIGHBOURS and open_edge:
        return same
    return 0


def is_wood_edge(chart: dict[str, Any], x: int, y: int, *, grid=None) -> bool:
    """The wood_edge rule for one cell (the hunting_grounds states)."""
    if not isinstance(chart, dict):
        return False
    if grid is None:
        grid = _grid_for(chart)
    return _wood_edge_score(chart, x, y, tuple(feature("hunting_grounds")["states"]), grid) > 0


def _crossing_land(chart: dict[str, Any], x: int, y: int, grid) -> list[tuple[int, int]]:
    """For a water cell: the land cells on both sides of each one-cell-wide axis run, as (x, y) pairs."""
    cell = _cell(chart, x, y, grid)
    if _state_of(cell) != WATER_STATE:
        return []
    found: list[tuple[int, int]] = []
    for dx, dy in CROSSING_AXES:
        before = _cell(chart, x - dx, y - dy, grid)
        after = _cell(chart, x + dx, y + dy, grid)
        if tile_walkable(before) and tile_walkable(after):
            found.append((x - dx, y - dy))
            found.append((x + dx, y + dy))
    return found


def is_ford(chart: dict[str, Any], x: int, y: int, *, grid=None) -> bool:
    """The water_crossing rule for one cell: a bridge, or water with land on both sides along one axis."""
    if not isinstance(chart, dict):
        return False
    if grid is None:
        grid = _grid_for(chart)
    cell = _cell(chart, x, y, grid)
    if not isinstance(cell, dict):
        return False
    if _state_of(cell) == BRIDGE_STATE:
        return True
    return bool(_crossing_land(chart, x, y, grid))


def _is_shore(chart: dict[str, Any], cell: dict[str, Any], x: int, y: int, grid) -> bool:
    if not tile_walkable(cell):
        return False
    return any(_state_of(other) == WATER_STATE for other in _neighbours(chart, x, y, grid))


def _known(chart: dict[str, Any], x: int, y: int, px: int, py: int) -> bool:
    key = f"{int(x)},{int(y)}"
    if key in {str(item) for item in (chart.get("visited") or [])}:
        return True
    if key in {str(item) for item in (chart.get("revealed") or [])}:
        return True
    return int(x) == int(px) and int(y) == int(py)


def _bearing_index(dx: int, dy: int) -> int:
    return _BEARING_INDEX.get(compass_word(dx, dy), -1)


def _candidate(
    feature_key: str,
    spec: dict[str, Any],
    *,
    x: int,
    y: int,
    state: str,
    source: str,
    score: int,
    name: str = "",
    discovered: bool | None = None,
    center: tuple[int, int],
    chart: dict[str, Any],
) -> dict[str, Any]:
    cx, cy = center
    return {
        "feature": feature_key,
        "x": int(x),
        "y": int(y),
        "state": str(state or ""),
        "source": source,
        "label": str(spec["label"]),
        "name": str(name or ""),
        "distance": max(abs(int(x) - cx), abs(int(y) - cy)),
        "score": int(score),
        "discovered": discovered,
        "known": _known(chart, x, y, cx, cy),
    }


def _add(found: dict[tuple[str, int, int], dict[str, Any]], cand: dict[str, Any]) -> None:
    """Dedupe by (feature, x, y): keep the higher score, the earlier entry on a tie."""
    key = (cand["feature"], cand["x"], cand["y"])
    have = found.get(key)
    if have is None or cand["score"] > have["score"]:
        found[key] = cand


def _within(x: Any, y: Any, center: tuple[int, int], horizon: int) -> bool:
    try:
        return max(abs(int(x) - center[0]), abs(int(y) - center[1])) <= horizon
    except (TypeError, ValueError):
        return False


def _scan_rows(
    chart: dict[str, Any],
    keys: list[str],
    center: tuple[int, int],
    horizon: int,
    grid,
    found: dict[tuple[str, int, int], dict[str, Any]],
) -> None:
    """Landmark rows, hidden_bases rows and lived knowledge markers."""
    landmarks = [row for row in (chart.get("landmarks") or []) if isinstance(row, dict)]
    bases = [row for row in (chart.get("hidden_bases") or []) if isinstance(row, dict)]
    knowledge = chart.get("knowledge") if isinstance(chart.get("knowledge"), dict) else {}
    danger = [row for row in (knowledge.get("danger") or []) if isinstance(row, dict)]
    for key in keys:
        spec = feature(key)
        rule = str(spec["rule"])
        if rule == "hidden_base":
            for row in bases:
                if not _within(row.get("x"), row.get("y"), center, horizon):
                    continue
                owner = str(row.get("owner") or "")
                discovered = bool(row.get("discovered"))
                _add(found, _candidate(
                    key, spec, x=row["x"], y=row["y"], state=_state_of(_cell(chart, row["x"], row["y"], grid)),
                    source="hidden_base", score=SCORE_CAMP,
                    name=HIDDEN_CAMP_NAMES.get(owner, HIDDEN_CAMP_DEFAULT_NAME) if discovered else "",
                    discovered=discovered, center=center, chart=chart,
                ))
            for row in landmarks:
                if str(row.get("kind") or "") != "hidden_base":
                    continue
                if not _within(row.get("x"), row.get("y"), center, horizon):
                    continue
                _add(found, _candidate(
                    key, spec, x=row["x"], y=row["y"], state=_state_of(row), source="landmark", score=SCORE_CAMP,
                    name=str(row.get("name") or ""), discovered=True, center=center, chart=chart,
                ))
            for row in danger:
                if not str(row.get("id") or "").startswith(LIVED_KNOWLEDGE_PREFIX):
                    continue
                if not _within(row.get("x"), row.get("y"), center, horizon):
                    continue
                _add(found, _candidate(
                    key, spec, x=row["x"], y=row["y"], state=str(row.get("kind") or "danger"), source="knowledge",
                    score=SCORE_CAMP, name=str(row.get("label") or ""), discovered=True, center=center, chart=chart,
                ))
            continue
        wanted = tuple(spec["landmarks"])
        if not wanted:
            continue
        for row in landmarks:
            if row.get("settlement_id") or str(row.get("kind") or "") == "hidden_base":
                continue
            state = _state_of(row)
            if state not in wanted or not _within(row.get("x"), row.get("y"), center, horizon):
                continue
            score = SCORE_WATERFALL if rule == "shore" else SCORE_STATE
            _add(found, _candidate(
                key, spec, x=row["x"], y=row["y"], state=state, source="landmark", score=score,
                name=str(row.get("name") or ""), discovered=None, center=center, chart=chart,
            ))


def _scan_cell(
    chart: dict[str, Any],
    keys: list[str],
    x: int,
    y: int,
    cell: dict[str, Any],
    center: tuple[int, int],
    grid,
    found: dict[tuple[str, int, int], dict[str, Any]],
) -> None:
    state = _state_of(cell)
    settlement = _is_settlement_cell(cell)
    for key in keys:
        spec = feature(key)
        rule = str(spec["rule"])
        states = tuple(spec["states"])
        if rule == "state":
            if not settlement and state in states:
                _add(found, _candidate(key, spec, x=x, y=y, state=state, source="tile", score=SCORE_STATE,
                                       center=center, chart=chart))
        elif rule == "wood_edge":
            score = _wood_edge_score(chart, x, y, states, grid)
            if score:
                _add(found, _candidate(key, spec, x=x, y=y, state=state, source="tile", score=score,
                                       center=center, chart=chart))
        elif rule == "water_crossing":
            if state == BRIDGE_STATE:
                _add(found, _candidate(key, spec, x=x, y=y, state=state, source="tile", score=SCORE_BRIDGE,
                                       center=center, chart=chart))
                continue
            sides = _crossing_land(chart, x, y, grid)
            for i in range(0, len(sides), 2):
                pair = sides[i:i + 2]
                # The land cell on the player's side: the nearer of the two, the first on a tie.
                near = min(pair, key=lambda p: (max(abs(p[0] - center[0]), abs(p[1] - center[1])), pair.index(p)))
                land = _cell(chart, near[0], near[1], grid)
                _add(found, _candidate(key, spec, x=near[0], y=near[1], state=_state_of(land), source="tile",
                                       score=SCORE_FORD, center=center, chart=chart))
        elif rule == "shore":
            if settlement:
                continue
            if state in states:
                _add(found, _candidate(key, spec, x=x, y=y, state=state, source="tile", score=SCORE_WATERFALL,
                                       center=center, chart=chart))
            elif _is_shore(chart, cell, x, y, grid):
                _add(found, _candidate(key, spec, x=x, y=y, state=state, source="tile", score=SCORE_SHORE,
                                       center=center, chart=chart))
        # hidden_base has no tile rule: its rows are read by _scan_rows.


def _sort_key(center: tuple[int, int]):
    def key(cand: dict[str, Any]) -> tuple[int, int, int, int, int]:
        dx, dy = cand["x"] - center[0], cand["y"] - center[1]
        return (cand["distance"], -cand["score"], _bearing_index(dx, dy), cand["x"], cand["y"])
    return key


def scan(
    chart: dict[str, Any],
    *,
    center: tuple[int, int] | None = None,
    horizon: int = WILD_HORIZON,
    features: Iterable[str] | None = None,
    include_hidden: bool = False,
) -> list[dict[str, Any]]:
    """Every wild candidate within ``horizon`` cells of ``center`` (the player), sorted by the choosing rule.

    include_hidden False drops undiscovered hidden_base candidates. Returns [] for a chart with no player
    (when no center is given) and for a board with no grid.
    """
    if not isinstance(chart, dict):
        return []
    if center is None:
        if not isinstance(chart.get("player"), dict):
            return []
        center = _player_xy(chart)
    try:
        center = (int(center[0]), int(center[1]))
    except (TypeError, ValueError, IndexError):
        return []
    try:
        horizon = int(horizon)
    except (TypeError, ValueError):
        horizon = WILD_HORIZON
    horizon = max(HORIZON_MIN, min(HORIZON_MAX, horizon))
    keys = [str(k) for k in features] if features is not None else [key for key, _spec in FEATURES]
    for key in keys:
        feature(key)  # KeyError early on an unknown feature
    grid = _grid_for(chart)
    if grid is None and str(chart.get("scale") or "") != "world":
        return []
    if grid is not None and not grid:
        return []
    found: dict[tuple[str, int, int], dict[str, Any]] = {}
    _scan_rows(chart, keys, center, horizon, grid, found)
    cx, cy = center
    for y in range(cy - horizon, cy + horizon + 1):
        for x in range(cx - horizon, cx + horizon + 1):
            cell = _cell(chart, x, y, grid)
            if not isinstance(cell, dict):
                continue
            _scan_cell(chart, keys, x, y, cell, center, grid, found)
    rows = [cand for cand in found.values() if include_hidden or cand["discovered"] is not False]
    rows.sort(key=_sort_key(center))
    return rows


def nearest(
    chart: dict[str, Any],
    feature_key: str,
    *,
    center: tuple[int, int] | None = None,
    horizon: int = WILD_HORIZON,
    include_hidden: bool = False,
) -> dict[str, Any] | None:
    rows = scan(chart, center=center, horizon=horizon, features=[feature_key], include_hidden=include_hidden)
    return rows[0] if rows else None


def distance_words(distance: int | None) -> str:
    try:
        value = int(distance or 0)
    except (TypeError, ValueError):
        value = 0
    for limit, words in DISTANCE_WORDS:
        if value <= limit:
            return words
    return DISTANCE_WORDS[-1][1]


# ---------------------------------------------------------------------------
# The answer
# ---------------------------------------------------------------------------


def _capitalise(text: str) -> str:
    text = str(text or "")
    return text[:1].upper() + text[1:] if text else text


def wording(
    feature_key: str,
    *,
    compass: str,
    distance: int | None,
    exact: bool,
    name: str = "",
    forbidden: bool = False,
    told: bool = True,
) -> str:
    """One sentence for the prompt; "" when not told."""
    if not told:
        return WORDING["none"]
    spec = feature(feature_key)
    fields = {
        "Noun": _capitalise(spec["noun"]),
        "compass": str(compass or ""),
        "dist": distance_words(distance),
        "name": str(name or ""),
    }
    here = fields["compass"] in {"", "here"}
    if forbidden:
        return WORDING["forbidden_here" if here else "forbidden"].format(**fields)
    if exact and here:
        return WORDING["exact_here"].format(**fields)
    if exact and fields["name"]:
        return WORDING["named"].format(**fields)
    if exact:
        return WORDING["exact"].format(**fields)
    if here:
        return WORDING["exact_here"].format(**fields)
    return WORDING["blurred"].format(**fields)


def _name_salt(text: str) -> int:
    value = 0
    for ch in str(text or ""):
        value = (value * 33 + ord(ch)) & 0xFFFFFFFF
    return value or 1


def _sign(value: int) -> int:
    return (value > 0) - (value < 0)


def _place(cand: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": PLACE_KIND,
        "feature": cand["feature"],
        "x": int(cand["x"]),
        "y": int(cand["y"]),
        "state": str(cand["state"]),
        "label": str(cand["label"]),
        "name": str(cand["name"]),
        "fine_x": 0,
        "fine_y": 0,
        "discovered": cand["discovered"],
        "source": str(cand["source"]),
    }


def resolve_wild_question(
    chart: dict[str, Any] | None,
    question: str,
    npc: dict[str, Any] | None,
    *,
    day: int = 1,
    gold: int = 0,
    player_xy: tuple[int, int] | None = None,
    roll: int | None = None,
    check_success: bool | None = None,
) -> dict[str, Any] | None:
    """The DirectionHint for a wild-place ask, or None when the chart is empty or the line is not one.

    Same signature as local_intel.resolve_direction minus the world-scale requirement: boards work too.
    Nothing here writes the chart, the journal or settings.
    """
    if not isinstance(chart, dict) or not chart:
        return None
    ask = parse_wild_question(question)
    if ask is None:
        return None
    if player_xy is None and not isinstance(chart.get("player"), dict):
        return None
    key = str(ask["feature"])
    spec = feature(key)
    public = bool(spec["public"])
    px, py = (int(player_xy[0]), int(player_xy[1])) if player_xy is not None else _player_xy(chart)
    npc_id = int((npc or {}).get("id") or 0)
    if npc and not npc_id:
        npc_id = _name_salt(str(npc.get("name") or "someone"))
    question_key = str(ask["text"])
    used_roll = direction_roll(int(day), npc_id, question_key) if roll is None else int(roll) % 100
    if check_success is None:
        check_success = stand_in_check(npc_id, int(day), question_key, int((npc or {}).get("trust") or 0))
    bribe = bool(ask["bribe"]) and int(gold) >= BRIBE_GOLD
    cand = nearest(chart, key, center=(px, py), include_hidden=not public)
    forbidden = (not public) and (cand is None or not bool(cand.get("discovered")))
    told, reason = will_tell(npc, forbidden=forbidden, roll=used_roll, check_success=bool(check_success), bribe=bribe)
    if cand is None:
        told = False
        reason = "nobody" if reason == "nobody" else "unknown"
    label = str(spec["label"])
    name = str((cand or {}).get("name") or label)
    hint: dict[str, Any] = {
        "told": bool(told and cand is not None),
        "specificity": str(ask["specificity"]),
        "good": key,
        "label": label,
        "name": name,
        "distance": None,
        "exact": False,
        "compass": "",
        "wording": "",
        "forbidden": forbidden,
        "reason": reason,
        "place": None,
        "x": None,
        "y": None,
    }
    if cand is None:
        return hint
    true_x, true_y = int(cand["x"]), int(cand["y"])
    told_x, told_y, near = blur_cell(px, py, true_x, true_y)
    if forbidden and near:
        # A forbidden answer is never exact: within EXACT_WITHIN the told cell is pulled back one cell
        # toward the asker, and an adjacent camp is told as "right here", so the true cell is never named.
        dx, dy = true_x - px, true_y - py
        if max(abs(dx), abs(dy)) >= 2:
            told_x, told_y = true_x - _sign(dx), true_y - _sign(dy)
        else:
            told_x, told_y = px, py
        near = False
    hint["compass"] = compass_word(told_x - px, told_y - py)
    if not hint["told"]:
        return hint
    distance = max(abs(told_x - px), abs(told_y - py))
    exact = bool(near and not forbidden)
    hint.update({
        "distance": distance,
        "exact": exact,
        "x": int(told_x),
        "y": int(told_y),
        "place": _place(cand),
        "wording": wording(
            key, compass=hint["compass"], distance=distance, exact=exact,
            name=str(cand.get("name") or ""), forbidden=forbidden, told=True,
        ),
    })
    return hint


def prompt_hint(hint: dict[str, Any] | None) -> dict[str, Any] | None:
    """What the prompt sees: local_intel.prompt_direction_hint, which strips the true place."""
    return prompt_direction_hint(hint)


def travel_candidate(hint: dict[str, Any] | None) -> tuple[dict[str, int], str, dict[str, str]] | None:
    """The turn_prompts.gate_after_turn candidate tuple (Target, label, source), or None unless told with x/y."""
    if not isinstance(hint, dict) or not hint.get("told"):
        return None
    if hint.get("x") is None or hint.get("y") is None:
        return None
    label = str(hint.get("label") or "")
    if hint.get("exact") and not hint.get("forbidden"):
        told_label = str(hint.get("name") or label or "the place you were told of")
    else:
        compass = str(hint.get("compass") or "").strip()
        told_label = (f"where you were pointed for {label}" if label else "where you were pointed") + (
            f", {compass}" if compass else ""
        )
    target = {"x": int(hint["x"]), "y": int(hint["y"])}
    source = {"kind": TRAVEL_SOURCE_KIND, "feature": str(hint.get("good") or "")}
    return target, told_label, source
