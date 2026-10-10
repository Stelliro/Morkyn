"""Tests for app/wild_places.py (TODO n22, built but not wired).

The module is a leaf: nothing in app/ or static/ imports it. These tests run it against hand-built
boards, one generated board and one generated world chart in a temporary database, with no model, no
network, no wall clock and no unseeded randomness.
"""
from __future__ import annotations

import copy
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-wild-places-test-"))
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

from app.db import connect, init_db  # noqa: E402
from app import local_intel, tile_world  # noqa: E402
from app import wild_places as wp  # noqa: E402
from app.tile_world import generate_map, generate_scaled_world, get_map  # noqa: E402

MODULE_PATH = ROOT / "app" / "wild_places.py"

_GENERATED_BOARD: dict | None = None
_GENERATED_WORLD: dict | None = None


def setUpModule():
    global _GENERATED_BOARD, _GENERATED_WORLD
    os.environ.update(_ENV)
    init_db()
    conn = connect()
    try:
        wp.ensure_schema(conn)
    finally:
        conn.close()
    # One generated board and one generated world chart for the whole module: generation writes the
    # world_maps row and takes the rolled map, so the world is rolled last and get_map(None) returns it.
    _GENERATED_BOARD = generate_map(preset_id="forest_march", seed=7, width=24, height=24, assign_images=False)
    generate_scaled_world(preset_id="forest_march", seed=20261007, density_percent=60, notice_percent=40)
    _GENERATED_WORLD = get_map(None)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_NOT_WALKABLE = {"water", "void", "lava", "cliff", "mountain", "volcano", "anomaly", "nebula"}


def _tile(x: int, y: int, state: str = "plains") -> dict:
    return {"x": x, "y": y, "state": state, "elevation": 0, "walkable": state not in _NOT_WALKABLE,
            "image_id": None, "image_path": "", "image_data_url": ""}


def _board(width: int = 24, height: int = 24, *, player=(10, 10), fill: str = "plains") -> dict:
    """A hand-built board in the get_map record shape: every tile plains unless painted."""
    grid = [[_tile(x, y, fill) for x in range(width)] for y in range(height)]
    return {
        "id": "board-test",
        "scale": "board",
        "width": width,
        "height": height,
        "player": {"x": player[0], "y": player[1]},
        "grid": grid,
        "tiles": [cell for row in grid for cell in row],
        "landmarks": [],
        "settlements_meta": [],
        "hidden_bases": [],
        "visited": [f"{player[0]},{player[1]}"],
        "revealed": [],
        "knowledge": {"settlements": [], "danger": [], "notes": [], "sources": []},
        "place_anchors": {},
    }


def _paint(chart: dict, x: int, y: int, state: str, **extra) -> dict:
    cell = chart["grid"][y][x]
    cell["state"] = state
    cell["walkable"] = state not in _NOT_WALKABLE
    cell.update(extra)
    return cell


def _npc(role: str = "farmer", attitude: str = "neutral", trust: int = 0, npc_id: int = 3, name: str = "Tam") -> dict:
    return {"id": npc_id, "code": f"N{npc_id}", "name": name, "role": role, "attitude": attitude, "trust": trust}


def _hidden_base(x: int, y: int, *, discovered: bool = False, owner: str = "bandit") -> dict:
    return {"id": "HB1", "x": x, "y": y, "owner": owner, "power_rank": 30, "hidden": True, "discovered": discovered}


HINT_KEYS = {"told", "specificity", "good", "label", "name", "distance", "exact", "compass", "forbidden",
             "reason", "wording", "place", "x", "y"}
PLACE_KEYS = {"kind", "feature", "x", "y", "state", "label", "name", "fine_x", "fine_y", "discovered", "source"}
CANDIDATE_KEYS = {"feature", "x", "y", "state", "source", "label", "name", "distance", "score", "discovered", "known"}


def _assert_hint_shape(case: unittest.TestCase, hint: dict) -> None:
    """contracts.md 1.16: the DirectionHint keys and types."""
    case.assertEqual(set(hint), HINT_KEYS)
    case.assertIsInstance(hint["told"], bool)
    case.assertIn(hint["specificity"], ("closest", "area"))
    for key in ("good", "label", "name", "compass", "reason", "wording"):
        case.assertIsInstance(hint[key], str)
    case.assertTrue(hint["name"])
    case.assertIsInstance(hint["exact"], bool)
    case.assertIsInstance(hint["forbidden"], bool)
    case.assertTrue(hint["distance"] is None or isinstance(hint["distance"], int))
    case.assertTrue(hint["x"] is None or isinstance(hint["x"], int))
    case.assertTrue(hint["y"] is None or isinstance(hint["y"], int))
    case.assertIn(hint["reason"], ("willing", "check", "bribe", "shady", "slip", "refused", "nobody", "unknown"))
    if hint["told"]:
        case.assertIsInstance(hint["place"], dict)
        case.assertEqual(set(hint["place"]), PLACE_KEYS)
        case.assertEqual(hint["place"]["kind"], "wild")
        case.assertEqual(hint["place"]["fine_x"], 0)
        case.assertEqual(hint["place"]["fine_y"], 0)
        case.assertIn(hint["place"]["source"], ("tile", "landmark", "hidden_base", "knowledge"))
        case.assertIsInstance(hint["x"], int)
        case.assertIsInstance(hint["y"], int)
        case.assertIsInstance(hint["distance"], int)
        case.assertLessEqual(len(hint["wording"]), 160)
    else:
        case.assertIsNone(hint["place"])
        case.assertIsNone(hint["x"])
        case.assertIsNone(hint["y"])
        case.assertIsNone(hint["distance"])
        case.assertEqual(hint["wording"], "")
        case.assertFalse(hint["exact"])


def _table_counts(conn) -> dict[str, int]:
    names = [
        r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    ]
    return {name: int(conn.execute(f'SELECT COUNT(*) AS n FROM "{name}"').fetchone()["n"]) for name in names}


# ---------------------------------------------------------------------------
# Leaf and schema
# ---------------------------------------------------------------------------


class LeafTests(unittest.TestCase):
    def test_module_is_a_leaf(self):
        needle = re.compile(r"app\.wild_places|import\s+wild_places|wild_places\b")
        offenders = []
        for folder in ("app", "static"):
            for path in (ROOT / folder).rglob("*"):
                if not path.is_file() or path.suffix not in {".py", ".js", ".html", ".css"}:
                    continue
                if path.resolve() == MODULE_PATH.resolve():
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
                if needle.search(text):
                    offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual(offenders, [], f"wild_places is referenced by {offenders}")
        doc = wp.__doc__ or ""
        self.assertIn("Status: built, not wired (TODO n22", doc)
        self.assertIn("Wiring (not done):", doc)
        self.assertIn("Turn on:", doc)
        self.assertIn("Tests: tests/test_wild_places.py", doc)

    def test_ensure_schema_is_a_no_op(self):
        class Untouchable:
            def __getattr__(self, name):
                raise AssertionError(f"ensure_schema touched the connection: {name}")

        self.assertIsNone(wp.ensure_schema(Untouchable()))
        conn = connect()
        try:
            self.assertIsNone(wp.ensure_schema(conn))
            self.assertIsNone(wp.ensure_schema(conn))
        finally:
            conn.close()

    def test_no_foreign_writes(self):
        board = _board()
        _paint(board, 5, 5, "cavern")
        conn = connect()
        try:
            before = _table_counts(conn)
            wp.ensure_schema(conn)
            hint = wp.resolve_wild_question(board, "where is the nearest cave?", _npc(), day=2, gold=5)
            wp.scan(_GENERATED_WORLD, horizon=3)
            after = _table_counts(conn)
        finally:
            conn.close()
        self.assertTrue(hint["told"])
        self.assertEqual(before, after)

    def test_private_imports_still_exist(self):
        for name in ("_cell_at", "_rebuild_grid", "_player_xy", "_DIRECTIONS", "NEIGHBOR_ORDER", "SETTLEMENT_STATES",
                     "tile_walkable"):
            self.assertTrue(hasattr(tile_world, name), name)
        for name in ("blur_cell", "compass_word", "will_tell", "direction_roll", "stand_in_check",
                     "prompt_direction_hint", "BRIBE_GOLD"):
            self.assertTrue(hasattr(local_intel, name), name)
        self.assertEqual(wp.BRIBE_GOLD, local_intel.BRIBE_GOLD)
        self.assertEqual(wp.BRIBE_RE.pattern, local_intel._BRIBE_RE.pattern)

    def test_hook_functions_named_in_docstring_exist(self):
        from app import turn_prompts

        doc = wp.__doc__ or ""
        for module, name in (
            (local_intel, "turn_direction_hint"), (local_intel, "apply_turn_intel"), (local_intel, "_record_hint"),
            (turn_prompts, "gate_after_turn"),
        ):
            self.assertIn(f"{name}()", doc)
            self.assertTrue(callable(getattr(module, name)), name)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


class ParseTests(unittest.TestCase):
    def test_parse_requires_an_ask(self):
        ask = wp.parse_wild_question("where are the hunting grounds?")
        self.assertEqual(ask["feature"], "hunting_grounds")
        self.assertEqual(ask["specificity"], "area")
        self.assertFalse(ask["bribe"])
        self.assertEqual(set(ask), {"feature", "specificity", "bribe", "text"})
        self.assertIsNone(wp.parse_wild_question("I hunt a boar"))
        self.assertEqual(wp.parse_wild_question("is there a ford near here")["feature"], "ford")
        ask = wp.parse_wild_question("nearest cave")
        self.assertEqual(ask["feature"], "cave")
        self.assertEqual(ask["specificity"], "closest")
        self.assertTrue(wp.is_wild_question("Which way to the marsh?"))
        self.assertFalse(wp.is_wild_question(""))
        self.assertFalse(wp.is_wild_question("the marsh is cold"))

    def test_feature_order_first_match_wins(self):
        self.assertEqual(wp.parse_wild_question("where can I hunt in the forest")["feature"], "hunting_grounds")
        self.assertEqual(wp.parse_wild_question("where is the bridge")["feature"], "ford")
        self.assertEqual(wp.features_in_text("where can I hunt in the forest"), ["hunting_grounds", "woods"])
        self.assertEqual([key for key, _spec in wp.FEATURES][:2], ["hunting_grounds", "ford"])

    def test_shop_questions_are_not_wild(self):
        self.assertIsNone(wp.parse_wild_question("where is the nearest food shop"))
        self.assertIsNone(wp.parse_wild_question("who sells rope here?"))

    def test_bare_camp_is_not_a_hidden_camp_ask(self):
        self.assertIsNone(wp.parse_wild_question("where can we make camp"))
        self.assertEqual(wp.parse_wild_question("where is the bandit camp")["feature"], "hidden_camp")
        self.assertNotIn("camp", wp.feature("hidden_camp")["words"].replace("bandit\\s+camp", "").replace(
            "hidden\\s+(?:camp|base)", ""))

    def test_bribe_is_read_from_the_line(self):
        self.assertTrue(wp.parse_wild_question("I bribe him: where is the hideout?")["bribe"])

    def test_feature_lookup(self):
        self.assertEqual(wp.feature("ford")["rule"], "water_crossing")
        with self.assertRaises(KeyError):
            wp.feature("volcano")
        for key, spec in wp.FEATURES:
            self.assertEqual(set(spec), {"words", "label", "noun", "rule", "states", "landmarks", "public"}, key)
            self.assertIn(spec["rule"], ("state", "wood_edge", "water_crossing", "shore", "hidden_base"))
        self.assertEqual(wp.WILD_HORIZON, 12)
        self.assertEqual(wp.EXACT_WITHIN, 4)
        self.assertEqual(wp.MIN_WOOD_NEIGHBOURS, 2)
        self.assertEqual(wp.DISTANCE_WORDS[-1][0], wp.WILD_HORIZON)

    def test_exact_within_matches_blur_cell(self):
        """EXACT_WITHIN documents local_intel.blur_cell's cutoff; this pins the two together."""
        for dist in range(0, wp.WILD_HORIZON + 1):
            _x, _y, near = local_intel.blur_cell(10, 10, 10 + dist, 10)
            self.assertEqual(near, dist <= wp.EXACT_WITHIN, dist)


# ---------------------------------------------------------------------------
# Scanning rules on boards
# ---------------------------------------------------------------------------


class ScanRuleTests(unittest.TestCase):
    def test_scan_state_rule_board(self):
        board = _board(player=(8, 8))
        _paint(board, 5, 5, "cavern")
        cand = wp.nearest(board, "cave")
        self.assertIsNotNone(cand)
        self.assertEqual(set(cand), CANDIDATE_KEYS)
        self.assertEqual((cand["x"], cand["y"]), (5, 5))
        self.assertEqual(cand["distance"], 3)
        self.assertEqual(cand["source"], "tile")
        self.assertEqual(cand["state"], "cavern")
        self.assertFalse(cand["known"])
        self.assertIsNone(cand["discovered"])

    def test_scan_skips_settlement_cells_and_keeps_landmark_words(self):
        board = _board(player=(10, 10))
        _paint(board, 12, 10, "forest", settlement_id="S1")
        _paint(board, 10, 13, "forest")
        cand = wp.nearest(board, "woods")
        self.assertEqual((cand["x"], cand["y"]), (10, 13))
        _paint(board, 10, 12, "ruins")
        _paint(board, 12, 12, "dungeon")
        self.assertEqual((wp.nearest(board, "ruin")["x"], wp.nearest(board, "ruin")["y"]), (10, 12))
        self.assertEqual((wp.nearest(board, "cave")["x"], wp.nearest(board, "cave")["y"]), (12, 12))

    def test_wood_edge_rule(self):
        board = _board(player=(10, 10))
        for y in range(5, 8):
            for x in range(5, 8):
                _paint(board, x, y, "forest")
        cand = wp.nearest(board, "hunting_grounds")
        self.assertEqual((cand["x"], cand["y"]), (7, 7))
        self.assertEqual(cand["score"], 3)
        self.assertEqual(cand["distance"], 3)
        self.assertTrue(wp.is_wood_edge(board, 7, 7))
        self.assertFalse(wp.is_wood_edge(board, 6, 6))  # the centre has no open edge
        lone = _board(player=(10, 10))
        _paint(lone, 12, 12, "forest")
        self.assertFalse(wp.is_wood_edge(lone, 12, 12))
        self.assertIsNone(wp.nearest(lone, "hunting_grounds"))
        self.assertEqual((wp.nearest(lone, "woods")["x"], wp.nearest(lone, "woods")["y"]), (12, 12))

    def test_ford_rule_one_cell_water_run(self):
        board = _board(player=(10, 10))
        _paint(board, 14, 10, "water")
        cand = wp.nearest(board, "ford")
        self.assertEqual((cand["x"], cand["y"]), (13, 10))
        self.assertEqual(cand["score"], 2)
        self.assertEqual(cand["state"], "plains")
        self.assertTrue(wp.is_ford(board, 14, 10))
        self.assertFalse(wp.is_ford(board, 10, 10))
        wide = _board(player=(10, 10))
        for y in range(wide["height"]):
            _paint(wide, 14, y, "water")
            _paint(wide, 15, y, "water")
        self.assertIsNone(wp.nearest(wide, "ford"))
        self.assertFalse(wp.is_ford(wide, 14, 10))
        _paint(board, 13, 7, "bridge")
        cand = wp.nearest(board, "ford")
        self.assertEqual((cand["x"], cand["y"]), (13, 7))
        self.assertEqual(cand["score"], 3)
        self.assertTrue(wp.is_ford(board, 13, 7))

    def test_shore_rule_prefers_waterfall(self):
        board = _board(player=(10, 10))
        _paint(board, 13, 10, "water")
        _paint(board, 10, 4, "waterfall")
        board["landmarks"].append({"x": 10, "y": 4, "state": "waterfall"})
        cand = wp.nearest(board, "spring")
        self.assertEqual(cand["distance"], 2)
        self.assertEqual(cand["x"], 12)
        self.assertEqual(cand["score"], 1)
        self.assertEqual(cand["source"], "tile")
        _paint(board, 10, 8, "waterfall")
        board["landmarks"].append({"x": 10, "y": 8, "state": "waterfall", "name": "Silver Fall"})
        cand = wp.nearest(board, "spring")
        self.assertEqual((cand["x"], cand["y"]), (10, 8))
        self.assertEqual(cand["score"], 3)
        self.assertEqual(cand["source"], "landmark")
        self.assertEqual(cand["name"], "Silver Fall")

    def test_shore_rule_skips_settlement_cells(self):
        """The settlement the player stands in is never the fresh-water answer, water neighbour or not."""
        board = _board(player=(10, 10))
        for row in board["grid"]:
            for cell in row:
                cell["state"] = "town"
                cell["settlement_id"] = "S1"
        _paint(board, 11, 10, "water")
        self.assertIsNone(wp.nearest(board, "spring"))
        hint = wp.resolve_wild_question(board, "where is fresh water?", _npc(), day=1)
        self.assertFalse(hint["told"])
        self.assertEqual(hint["reason"], "unknown")
        _paint(board, 12, 10, "plains", settlement_id=None)
        cand = wp.nearest(board, "spring")
        self.assertEqual((cand["x"], cand["y"]), (12, 10))
        self.assertEqual(cand["score"], 1)
        # A waterfall stamped on a settlement cell is a town feature, not a wild one.
        _paint(board, 10, 12, "waterfall")
        self.assertEqual((wp.nearest(board, "spring")["x"], wp.nearest(board, "spring")["y"]), (12, 10))
        # The generated board's start cell is a town with water beside it (forest_march, seed 7).
        gen = _GENERATED_BOARD
        hint = wp.resolve_wild_question(gen, "where is fresh water?", _npc(), day=1)
        if hint["told"]:
            cell = tile_world._cell_at(gen, hint["place"]["x"], hint["place"]["y"])
            self.assertFalse(cell.get("settlement_id"), cell)
            self.assertNotIn(cell.get("state"), wp.SETTLEMENT_CELL_STATES)

    def test_hidden_camp_undiscovered_not_in_default_scan(self):
        board = _board(player=(10, 10))
        board["hidden_bases"].append(_hidden_base(12, 12))
        self.assertEqual(wp.scan(board, features=["hidden_camp"]), [])
        rows = wp.scan(board, features=["hidden_camp"], include_hidden=True)
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["discovered"])
        self.assertEqual(rows[0]["name"], "")
        self.assertEqual(rows[0]["source"], "hidden_base")

    def test_knowledge_lived_danger_counts_as_discovered_camp(self):
        board = _board(player=(10, 10))
        board["knowledge"]["danger"].append(
            {"id": "lived-HB1", "x": 13, "y": 9, "label": "Bandit stretch", "kind": "danger", "source": "lived"}
        )
        board["knowledge"]["danger"].append({"id": "other", "x": 11, "y": 11, "label": "Rough country"})
        cand = wp.nearest(board, "hidden_camp")
        self.assertEqual(cand["source"], "knowledge")
        self.assertTrue(cand["discovered"])
        self.assertEqual(cand["name"], "Bandit stretch")
        self.assertEqual((cand["x"], cand["y"]), (13, 9))

    def test_choosing_order_distance_score_bearing(self):
        board = _board(player=(10, 10))
        _paint(board, 10, 7, "hill")  # north, distance 3
        _paint(board, 13, 10, "hill")  # east, distance 3
        _paint(board, 10, 12, "hill")  # south, distance 2
        rows = wp.scan(board, features=["high_ground"])
        self.assertEqual([(r["x"], r["y"]) for r in rows], [(10, 12), (10, 7), (13, 10)])

    def test_horizon_and_center_and_malformed_charts(self):
        board = _board(player=(10, 10))
        _paint(board, 23, 10, "cavern")  # distance 13: one past WILD_HORIZON
        self.assertIsNone(wp.nearest(board, "cave"))
        self.assertEqual(wp.nearest(board, "cave", horizon=99)["x"], 23)  # clamped to 24
        self.assertEqual(wp.nearest(board, "cave", center=(20, 10))["distance"], 3)
        _paint(board, 22, 10, "cavern")  # distance 12: on the horizon, so scanned
        self.assertEqual(wp.nearest(board, "cave")["distance"], wp.WILD_HORIZON)
        self.assertEqual(wp.scan({"scale": "board", "grid": [], "tiles": []}), [])
        self.assertEqual(wp.scan({"scale": "board", "player": {"x": 1, "y": 1}, "grid": [], "tiles": [], "width": 0}), [])
        self.assertEqual(wp.scan(None), [])
        self.assertEqual(wp.scan(board, features=[]), [])
        with self.assertRaises(KeyError):
            wp.scan(board, features=["volcano"])
        self.assertFalse(wp.is_ford(board, -1, -1))
        self.assertFalse(wp.is_wood_edge(board, 99, 99))

    def test_distance_words(self):
        self.assertEqual(wp.distance_words(0), "just over there")
        self.assertEqual(wp.distance_words(2), "just over there")
        self.assertEqual(wp.distance_words(3), "close by")
        self.assertEqual(wp.distance_words(8), "an hour or two out")
        self.assertEqual(wp.distance_words(12), "half a day out")
        self.assertEqual(wp.distance_words(40), "half a day out")
        self.assertEqual(wp.distance_words(None), "just over there")


# ---------------------------------------------------------------------------
# Resolving
# ---------------------------------------------------------------------------


class ResolveTests(unittest.TestCase):
    def test_resolve_public_feature_willing_npc(self):
        board = _board(player=(10, 10))
        _paint(board, 10, 7, "cavern")
        hint = wp.resolve_wild_question(board, "where is the nearest cave?", _npc(), day=3, gold=0)
        _assert_hint_shape(self, hint)
        self.assertTrue(hint["told"])
        self.assertTrue(hint["exact"])
        self.assertEqual(hint["reason"], "willing")
        self.assertEqual(hint["compass"], "north")
        self.assertEqual(hint["good"], "cave")
        self.assertEqual(hint["label"], "a cave")
        self.assertEqual(hint["name"], "a cave")
        self.assertEqual(hint["specificity"], "closest")
        self.assertFalse(hint["forbidden"])
        self.assertEqual((hint["x"], hint["y"], hint["distance"]), (10, 7, 3))
        self.assertEqual(hint["place"]["kind"], "wild")
        self.assertEqual(hint["place"]["feature"], "cave")
        self.assertEqual((hint["place"]["x"], hint["place"]["y"]), (10, 7))
        self.assertEqual(hint["wording"], wp.WORDING["exact"].format(Noun="A cave", compass="north", dist="close by", name=""))
        self.assertEqual(hint["wording"], "A cave lies north of here, close by.")

    def test_resolve_blurs_far_target(self):
        board = _board(player=(10, 10))
        _paint(board, 10, 1, "cavern")
        hint = wp.resolve_wild_question(board, "where is a cave?", _npc(), day=3)
        _assert_hint_shape(self, hint)
        self.assertTrue(hint["told"])
        self.assertFalse(hint["exact"])
        self.assertLess(hint["distance"], 9)
        self.assertNotEqual((hint["x"], hint["y"]), (10, 1))
        self.assertEqual((hint["place"]["x"], hint["place"]["y"]), (10, 1))
        self.assertEqual(hint["wording"], wp.WORDING["blurred"].format(
            Noun="A cave", compass="north", dist=wp.distance_words(hint["distance"]), name=""))

    def test_named_landmark_wording(self):
        board = _board(player=(10, 10))
        _paint(board, 12, 12, "monolith")
        board["landmarks"].append({"x": 12, "y": 12, "state": "monolith", "name": "The Grey Sisters"})
        hint = wp.resolve_wild_question(board, "do you know of any standing stones?", _npc(), day=1)
        self.assertTrue(hint["exact"])
        self.assertEqual(hint["name"], "The Grey Sisters")
        self.assertEqual(hint["wording"], "The Grey Sisters is southeast of here, just over there.")

    def test_resolve_forbidden_camp_needs_shady(self):
        board = _board(player=(10, 10))
        board["hidden_bases"].append(_hidden_base(13, 10))
        refused = wp.resolve_wild_question(board, "where is the bandit hideout?", _npc(role="farmer"), day=1, roll=80)
        _assert_hint_shape(self, refused)
        self.assertFalse(refused["told"])
        self.assertEqual(refused["reason"], "refused")
        self.assertTrue(refused["forbidden"])
        told = wp.resolve_wild_question(board, "where is the bandit hideout?", _npc(role="smuggler"), day=1, roll=10)
        _assert_hint_shape(self, told)
        self.assertTrue(told["told"])
        self.assertEqual(told["reason"], "shady")
        self.assertTrue(told["forbidden"])
        self.assertFalse(told["exact"])
        self.assertEqual((told["x"], told["y"]), (12, 10))  # pulled back one cell from the true (13, 10)
        self.assertEqual((told["place"]["x"], told["place"]["y"]), (13, 10))
        self.assertFalse(told["place"]["discovered"])
        self.assertEqual(told["wording"], wp.WORDING["forbidden"].format(
            Noun="The camp", compass="east", dist="just over there", name=""))
        self.assertIsNone(wp.travel_candidate(refused))
        target, label, source = wp.travel_candidate(told)
        self.assertEqual(label, "where you were pointed for the camp, east")
        # One cell away the answer is "right here": the true cell is never named, so apply_hint_to_map
        # and travel_candidate cannot give the camp away.
        near = _board(player=(10, 10))
        near["hidden_bases"].append(_hidden_base(11, 10))
        close = wp.resolve_wild_question(near, "where is the bandit hideout?", _npc(role="smuggler"), day=1, roll=10)
        _assert_hint_shape(self, close)
        self.assertTrue(close["told"])
        self.assertFalse(close["exact"])
        self.assertEqual((close["place"]["x"], close["place"]["y"]), (11, 10))
        self.assertNotEqual((close["x"], close["y"]), (close["place"]["x"], close["place"]["y"]))
        self.assertEqual((close["x"], close["y"], close["distance"]), (10, 10, 0))
        self.assertEqual(close["compass"], "here")
        self.assertEqual(close["wording"], wp.WORDING["forbidden_here"])

    def test_discovered_camp_is_public(self):
        board = _board(player=(10, 10))
        board["hidden_bases"].append(_hidden_base(13, 10, discovered=True))
        hint = wp.resolve_wild_question(board, "where is the bandit camp?", _npc(role="farmer"), day=1, roll=80)
        self.assertTrue(hint["told"])
        self.assertFalse(hint["forbidden"])
        self.assertEqual(hint["reason"], "willing")
        self.assertEqual(hint["name"], "Bandit camp")
        self.assertTrue(hint["exact"])
        self.assertTrue(hint["place"]["discovered"])
        self.assertEqual(hint["wording"], "Bandit camp is east of here, close by.")
        civ = _board(player=(10, 10))
        civ["hidden_bases"].append(_hidden_base(13, 10, discovered=True, owner="civilian"))
        self.assertEqual(wp.resolve_wild_question(civ, "where is the hideout?", _npc(), day=1)["name"], "Hidden camp")

    def test_resolve_unknown_when_nothing_in_horizon(self):
        board = _board(player=(10, 10))
        hint = wp.resolve_wild_question(board, "where is the nearest cave?", _npc(), day=1)
        _assert_hint_shape(self, hint)
        self.assertFalse(hint["told"])
        self.assertEqual(hint["reason"], "unknown")
        self.assertEqual(hint["wording"], "")
        self.assertEqual(hint["compass"], "")
        nobody = wp.resolve_wild_question(board, "where is the nearest cave?", None, day=1)
        self.assertFalse(nobody["told"])
        self.assertEqual(nobody["reason"], "nobody")

    def test_resolve_none_for_non_question(self):
        board = _board()
        self.assertIsNone(wp.resolve_wild_question(board, "I sharpen my knife by the fire", _npc()))
        self.assertIsNone(wp.resolve_wild_question(None, "where is the cave?", _npc()))
        self.assertIsNone(wp.resolve_wild_question({}, "where is the cave?", _npc()))
        self.assertIsNone(wp.resolve_wild_question({"scale": "board", "grid": [], "tiles": []}, "where is the cave?", _npc()))

    def test_hostile_npc_uses_check_bribe_and_roll(self):
        board = _board(player=(10, 10))
        _paint(board, 10, 7, "cavern")
        wary = _npc(attitude="wary")
        self.assertEqual(wp.resolve_wild_question(board, "where is the cave?", wary, roll=80, check_success=True)["reason"], "check")
        refused = wp.resolve_wild_question(board, "where is the cave?", wary, roll=80, check_success=False)
        self.assertFalse(refused["told"])
        self.assertEqual(refused["reason"], "refused")
        bribed = wp.resolve_wild_question(board, "I bribe him. where is the cave?", wary, gold=wp.BRIBE_GOLD, roll=80,
                                          check_success=False)
        self.assertEqual(bribed["reason"], "bribe")
        poor = wp.resolve_wild_question(board, "I bribe him. where is the cave?", wary, gold=wp.BRIBE_GOLD - 1, roll=80,
                                        check_success=False)
        self.assertEqual(poor["reason"], "refused")
        self.assertEqual(wp.resolve_wild_question(board, "where is the cave?", wary, roll=10, check_success=False)["reason"],
                         "willing")

    def test_standing_on_the_feature(self):
        board = _board(player=(10, 10))
        _paint(board, 10, 10, "hill")
        hint = wp.resolve_wild_question(board, "where is high ground?", _npc(), day=1)
        self.assertTrue(hint["told"])
        self.assertEqual(hint["compass"], "here")
        self.assertEqual(hint["distance"], 0)
        self.assertEqual(hint["wording"], "High ground is right here.")
        self.assertEqual(wp.wording("hidden_camp", compass="here", distance=0, exact=False, forbidden=True),
                         wp.WORDING["forbidden_here"])
        self.assertEqual(wp.wording("road", compass="east", distance=3, exact=True, told=False), "")

    def test_world_chart_terrain_features(self):
        chart = _GENERATED_WORLD
        self.assertEqual(chart.get("scale"), "world")
        self.assertEqual(chart.get("landmarks"), [])
        self.assertEqual(chart.get("hidden_bases"), [])
        woods = wp.nearest(chart, "woods")
        self.assertIsNotNone(woods)
        self.assertEqual(woods["source"], "tile")
        self.assertIn(woods["state"], wp.feature("woods")["states"])
        self.assertLessEqual(woods["distance"], wp.WILD_HORIZON)
        self.assertIsNone(wp.nearest(chart, "cave"))
        self.assertIsNone(wp.nearest(chart, "hidden_camp", include_hidden=True))
        hint = wp.resolve_wild_question(chart, "where are the woods?", _npc(), day=1)
        self.assertTrue(hint["told"])
        _assert_hint_shape(self, hint)
        self.assertEqual((hint["place"]["x"], hint["place"]["y"]), (woods["x"], woods["y"]))
        # The settlement the player stands in is never a wild answer.
        for cand in wp.scan(chart):
            self.assertFalse(tile_world._cell_at(chart, cand["x"], cand["y"]).get("city_id"), cand)

    def test_generated_board_answers_without_raising(self):
        board = _GENERATED_BOARD
        self.assertEqual(board.get("scale"), "board")
        rows = wp.scan(board)
        self.assertIsInstance(rows, list)
        for cand in rows:
            self.assertEqual(set(cand), CANDIDATE_KEYS)
            self.assertLessEqual(cand["distance"], wp.WILD_HORIZON)
        asks = {
            "hunting_grounds": "where are the hunting grounds?", "ford": "is there a ford nearby?",
            "cave": "where is the nearest cave?", "ruin": "know of any ruins?", "stones": "where are the old stones?",
            "spring": "where is fresh water?", "high_ground": "which way to high ground?",
            "woods": "where are the woods?", "marsh": "where is the marsh?", "road": "where is the road?",
            "hidden_camp": "where is the bandit hideout?",
        }
        self.assertEqual(set(asks), {key for key, _spec in wp.FEATURES})
        for key, line in asks.items():
            hint = wp.resolve_wild_question(board, line, _npc(role="smuggler"), day=1)
            self.assertIsNotNone(hint, key)
            self.assertEqual(hint["good"], key)
            _assert_hint_shape(self, hint)

    def test_pure_no_chart_mutation(self):
        board = _board(player=(10, 10))
        _paint(board, 10, 7, "cavern")
        board["hidden_bases"].append(_hidden_base(13, 10))
        before = copy.deepcopy(board)
        wp.resolve_wild_question(board, "where is the nearest cave?", _npc(), day=3)
        wp.resolve_wild_question(board, "where is the bandit hideout?", _npc(role="smuggler"), day=3)
        wp.scan(board, include_hidden=True)
        self.assertEqual(board, before)
        gen = _GENERATED_BOARD
        before = copy.deepcopy(gen)
        wp.resolve_wild_question(gen, "where are the woods?", _npc(), day=3)
        self.assertEqual(gen, before)

    def test_determinism_same_day_same_npc(self):
        board = _board(player=(10, 10))
        _paint(board, 10, 7, "cavern")
        wary = _npc(attitude="wary", npc_id=11)
        one = wp.resolve_wild_question(board, "where is the cave?", wary, day=4)
        two = wp.resolve_wild_question(board, "where is the cave?", wary, day=4)
        self.assertEqual(one, two)
        told_days = set()
        for day in range(1, 40):
            later = wp.resolve_wild_question(board, "where is the cave?", wary, day=day)
            for key in ("good", "label", "specificity", "forbidden"):
                self.assertEqual(later[key], one[key])
            told_days.add(later["told"])
            if later["told"] and one["told"]:
                # Only told and reason may move with the day's roll; a told answer names the same cell.
                self.assertEqual({k: v for k, v in later.items() if k != "reason"},
                                 {k: v for k, v in one.items() if k != "reason"})
        self.assertEqual(told_days, {True, False})  # a wary person's answer depends on the day's roll


# ---------------------------------------------------------------------------
# Prompt and travel shapes
# ---------------------------------------------------------------------------


class ShapeTests(unittest.TestCase):
    def _hint(self, distance_cells: int) -> dict:
        board = _board(player=(10, 10))
        _paint(board, 10, 10 - distance_cells, "cavern")
        return wp.resolve_wild_question(board, "where is the cave?", _npc(), day=1)

    def test_prompt_hint_strips_place(self):
        hint = self._hint(3)
        shown = wp.prompt_hint(hint)
        self.assertNotIn("place", shown)
        self.assertEqual(shown, local_intel.prompt_direction_hint(hint))
        self.assertEqual((shown["x"], shown["y"]), (hint["x"], hint["y"]))
        self.assertIsNone(wp.prompt_hint(None))

    def test_travel_candidate_shapes(self):
        exact = self._hint(3)
        target, label, source = wp.travel_candidate(exact)
        self.assertEqual(target, {"x": 10, "y": 7})
        self.assertIsInstance(target["x"], int)
        self.assertIsInstance(target["y"], int)
        self.assertEqual(label, "a cave")
        self.assertEqual(source, {"kind": "direction_hint", "feature": "cave"})
        blurred = self._hint(9)
        target, label, source = wp.travel_candidate(blurred)
        self.assertEqual(target, {"x": blurred["x"], "y": blurred["y"]})
        self.assertEqual(label, "where you were pointed for a cave, north")
        self.assertIsNone(wp.travel_candidate(None))
        self.assertIsNone(wp.travel_candidate({"told": False}))
        self.assertIsNone(wp.travel_candidate({"told": True, "x": None, "y": 3}))

    def test_gate_after_turn_inline_label_differs_from_travel_candidate(self):
        """turn_prompts.gate_after_turn builds a blurred label from hint["good"], the FEATURES key, so a wild
        hint must go through travel_candidate (the docstring's hook line) to read as spoken words."""
        board = _board(player=(10, 10))
        for y in range(0, 3):
            for x in range(9, 12):
                _paint(board, x, y, "forest")
        hint = wp.resolve_wild_question(board, "where are the hunting grounds?", _npc(), day=1)
        self.assertTrue(hint["told"])
        self.assertFalse(hint["exact"])
        self.assertEqual(hint["place"]["kind"], "wild")
        # The live rule, copied from gate_after_turn's direction_hint branch.
        good = str(hint.get("good") or hint.get("label") or "").strip()
        compass = str(hint.get("compass") or "").strip()
        inline = (f"where you were pointed for {good}" if good else "where you were pointed") + (
            f", {compass}" if compass else ""
        )
        target, label, source = wp.travel_candidate(hint)
        self.assertEqual(inline, "where you were pointed for hunting_grounds, north")
        self.assertEqual(label, "where you were pointed for hunting grounds, north")
        self.assertNotEqual(inline, label)
        self.assertNotIn("_", label)
        self.assertEqual(target, {"x": hint["x"], "y": hint["y"]})
        self.assertEqual(source, {"kind": "direction_hint", "feature": "hunting_grounds"})

    def test_hint_rides_apply_hint_to_map_and_record_told(self):
        """The existing map side effects accept a wild hint unchanged (copy of the chart; nothing saved)."""
        from app.town_moves import record_told

        board = _board(player=(10, 10))
        _paint(board, 10, 7, "cavern")
        hint = wp.resolve_wild_question(board, "where is the cave?", _npc(), day=1)
        chart = copy.deepcopy(board)
        applied = local_intel.apply_hint_to_map(chart, hint, save=False)
        self.assertTrue(applied["told"])
        self.assertIn("10,7", chart["revealed"])
        self.assertEqual(record_told(None, chart, hint["place"], 1), "")


if __name__ == "__main__":
    unittest.main()
