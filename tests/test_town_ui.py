"""Town grid, slice C (docs/TownGrid.md 8): the map zooms into the town.

The player asked to zoom into a town and see its sub-grid: roads to follow and
plots that may be shops. Slices A and B built the grid and the engine walk.
These tests hold the browser side: the Streets view reads the server's road
mask (zlib + base64, the same packing town_grid stores), previews the walk on
the roads the player knows, walks arrow keys to the next junction, keeps long
travel behind the scene gate, writes "Go to" and "Go in" as sentences (going
in is a turn) and marks the one immediate item, "Walk here now", with the red
moon. Entering a town zooms in once unless the player chose World since.

The JS functions are lifted out of static/app.js and run in node with stubs,
the same way tests/test_map_move_error_message.py runs apiErrorMessage.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

# Only app.town_grid._pack is imported, but nothing app-side may see the live data/ paths.
os.environ.update(isolated_data_env(tempfile.mkdtemp(prefix="morkyn-town-ui-")))
APP_JS = ROOT / "static" / "app.js"
INDEX = ROOT / "static" / "index.html"
INTERACT = ROOT / "static" / "ui" / "interact.js"
STYLES = ROOT / "static" / "styles.css"
SKIN = ROOT / "static" / "ui" / "skin.css"

TOWN_FUNCTIONS = (
    "townPrefGet",
    "townPrefSet",
    "townPositionFromState",
    "townStreetsActive",
    "townAutoZoomCheck",
    "townDecodeRoads",
    "townCellAt",
    "townPreviewPath",
    "townTargetName",
    "townCanEnter",
    "townWalkRefusal",
    "townArrowWalk",
    "townCanvasMenu",
)


def _function(text: str, name: str) -> str:
    match = re.search(rf"^(?:async )?function {name}\(.*?^\}}\n", text, re.M | re.S)
    assert match, f"{name} missing from static/app.js"
    return match.group(0)


def _sources() -> str:
    text = APP_JS.read_text(encoding="utf-8")
    return "\n".join(_function(text, name) for name in TOWN_FUNCTIONS)


PRELUDE = r"""
const TOWN_ZOOM_PREF_KEY = "morkyn-town-autozoom-v1";
const TOWN_ROAD_CACHE_MAX = 24;
const townRoadCache = new Map();
const store = new Map();
globalThis.window = {
  localStorage: { getItem: (k) => (store.has(k) ? store.get(k) : null), setItem: (k, v) => store.set(k, String(v)), removeItem: (k) => store.delete(k) },
  setTimeout,
};
const banner = { textContent: "" };
const canvasStub = { getBoundingClientRect: () => ({ left: 0, top: 0, width: 300, height: 300 }) };
globalThis.document = {
  querySelector: (sel) => (sel === "#mapTravelBanner" ? banner : sel === "#settlementCanvas" ? canvasStub : null),
};
let state = {};
let mapViewMode = "world";
let settlementZoom = "city";
let settlementData = null;
let settlementPick = "";
let townData = null;
let townFocus = null;
let townPan = { x: 0, y: 0 };
let townLastCity;
let movementLocked = false;
let mapBlank = false;
let travelReady = true;
const walks = [];
const written = [];
let viewSwitches = 0;
function townWalk(target) { walks.push(target); }
function townGoIn(plot) { written.push(`I go into ${townTargetName(plot)}.`); }
function townSelectAt() {}
function insertRawToken(text) { written.push(text); }
function setMapViewMode(mode) { mapViewMode = mode; viewSwitches += 1; }
let hitStub = null;
function townHitTest() { return hitStub; }
"""


def _mask(side: int, roads: dict[tuple[int, int], int]) -> list[int]:
    out = [0] * (side * side)
    for (x, y), cls in roads.items():
        out[y * side + x] = cls
    return out


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class StreetsLogicInNode(unittest.TestCase):
    def _run(self, body: str):
        script = PRELUDE + _sources() + "\n(async () => {\n" + body + "\n})().catch((e) => { console.error(e); process.exit(1); });\n"
        done = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout.strip().splitlines()[-1])

    def test_road_mask_decodes_the_server_packing(self):
        from app.town_grid import _pack

        side = 16
        raw = bytes((i * 7) % 5 for i in range(side * side))
        out = self._run(
            f"const bytes = await townDecodeRoads({json.dumps(_pack(raw))});\n"
            "process.stdout.write(JSON.stringify(Array.from(bytes || [])));"
        )
        self.assertEqual(out, list(raw))

    def test_preview_path_follows_known_roads_only(self):
        side = 8
        # An L of road: along y=1 from x=1..6, then down x=6 to y=6. A separate stub at (1, 6).
        roads = {(x, 1): 3 for x in range(1, 7)}
        roads.update({(6, y): 3 for y in range(1, 7)})
        roads[(1, 6)] = 3
        cell = {"cx": 0, "cy": 0, "side": side}
        out = self._run(
            f"const cell = {json.dumps(cell)}; cell._mask = Uint8Array.from({json.dumps(_mask(side, roads))});\n"
            "const path = townPreviewPath(cell, [1, 1], [6, 6]);\n"
            "const none = townPreviewPath(cell, [1, 1], [1, 6]);\n"
            "process.stdout.write(JSON.stringify({path, none}));"
        )
        self.assertEqual(out["path"][0], [1, 1])
        self.assertEqual(out["path"][-1], [6, 6])
        self.assertEqual(len(out["path"]), 11)
        for x, y in out["path"]:
            self.assertIn((x, y), roads)
        self.assertIsNone(out["none"])

    def _arrow(self, roads, side, player, dx, dy, neighbours=(), ready=True):
        cells = [{"cx": 10, "cy": 10, "side": side, "known": True}]
        cells += [dict(c) for c in neighbours]
        return self._run(
            f"townData = {{ player: {json.dumps(player)}, cells: {json.dumps(cells)} }};\n"
            f"townData.cells[0]._mask = Uint8Array.from({json.dumps(_mask(side, roads))});\n"
            f"travelReady = {json.dumps(ready)};\n"
            f"townArrowWalk({dx}, {dy});\n"
            "process.stdout.write(JSON.stringify({walks, banner: banner.textContent}));"
        )

    def test_arrow_walks_to_the_next_junction(self):
        side = 12
        roads = {(x, 5): 3 for x in range(0, 12)}
        roads.update({(7, y): 3 for y in range(0, 5)})  # a side street meets the road at x=7
        out = self._arrow(roads, side, {"cx": 10, "cy": 10, "fx": 2, "fy": 5}, 1, 0)
        self.assertEqual(out["walks"], [{"cx": 10, "cy": 10, "fx": 7, "fy": 5}])

    def test_arrow_with_no_road_that_way_does_not_walk(self):
        side = 12
        roads = {(x, 5): 3 for x in range(0, 12)}
        out = self._arrow(roads, side, {"cx": 10, "cy": 10, "fx": 2, "fy": 5}, 0, -1)
        self.assertEqual(out["walks"], [])
        self.assertIn("No road", out["banner"])

    def test_arrow_off_the_edge_enters_the_next_cell_at_the_matching_tile(self):
        side = 12
        roads = {(x, 6): 3 for x in range(0, 12)}
        east = {"cx": 11, "cy": 10, "side": 24, "known": True}
        out = self._arrow(roads, side, {"cx": 10, "cy": 10, "fx": 11, "fy": 6}, 1, 0, neighbours=[east])
        self.assertEqual(out["walks"], [{"cx": 11, "cy": 10, "fx": 0, "fy": 13}])

    def test_leaving_the_cell_waits_for_the_scene(self):
        side = 12
        roads = {(x, 6): 3 for x in range(0, 12)}
        east = {"cx": 11, "cy": 10, "side": 12, "known": True}
        out = self._arrow(roads, side, {"cx": 10, "cy": 10, "fx": 11, "fy": 6}, 1, 0, neighbours=[east], ready=False)
        self.assertEqual(out["walks"], [])
        self.assertIn("scene", out["banner"])

    def _menu(self, plot, *, cell=(10, 10), ready=True):
        return self._run(
            "mapViewMode = 'settlement'; settlementZoom = 'streets'; settlementData = { town: { zoomable: true } };\n"
            "townData = { player: { cx: 10, cy: 10, fx: 1, fy: 1 }, cells: [] };\n"
            f"travelReady = {json.dumps(ready)};\n"
            f"hitStub = {{ cell: {{ cx: {cell[0]}, cy: {cell[1]} }}, fx: 3, fy: 3, plot: {json.dumps(plot)} }};\n"
            "const spec = townCanvasMenu({ clientX: 0, clientY: 0 });\n"
            "const items = spec ? spec.items.map((i) => ({ text: i.text, danger: !!i.danger })) : null;\n"
            "for (const item of spec ? spec.items : []) if (!item.danger && item.text !== 'Details') item.run();\n"
            "const moon = spec ? spec.items.find((i) => i.danger) : null; if (moon) moon.run();\n"
            "process.stdout.write(JSON.stringify({ items, written, walks }));"
        )

    def test_menu_writes_sentences_and_only_walk_here_now_acts(self):
        plot = {"id": "C1.0.0.5", "k": "shop", "vk": "bakery", "label": "bakery", "name": "Wheel Street Bakery"}
        out = self._menu(plot)
        texts = [i["text"] for i in out["items"]]
        self.assertEqual(texts[:3], ["Go to Wheel Street Bakery", "Go in", "Walk here now"])
        self.assertEqual([i["text"] for i in out["items"] if i["danger"]], ["Walk here now"])
        self.assertEqual(out["written"], ["I walk to Wheel Street Bakery.", "I go into Wheel Street Bakery."])
        self.assertEqual(out["walks"], [{"plot_id": "C1.0.0.5"}])

    def test_menu_for_an_unnamed_house_has_no_go_in(self):
        out = self._menu({"id": "C1.0.0.9", "k": "house", "label": "house"})
        texts = [i["text"] for i in out["items"]]
        self.assertIn("Go to the house", texts)
        self.assertNotIn("Go in", texts)

    def test_menu_offers_no_immediate_walk_out_of_the_cell_while_the_scene_holds(self):
        plot = {"id": "C1.1.0.5", "k": "shop", "label": "bakery", "name": "Far Bakery"}
        out = self._menu(plot, cell=(11, 10), ready=False)
        self.assertNotIn("Walk here now", [i["text"] for i in out["items"]])
        self.assertEqual(out["walks"], [])

    def test_entering_a_town_zooms_in_once_unless_world_was_chosen(self):
        out = self._run(
            "const r = [];\n"
            "state = { settings: {} }; r.push(townAutoZoomCheck());\n"
            "state = { settings: { town_position: JSON.stringify({ city_id: 'C3', cx: 1, cy: 1 }) } };\n"
            "r.push(townAutoZoomCheck()); r.push(settlementZoom, mapViewMode);\n"
            "r.push(townAutoZoomCheck());\n"  # still in the same town: no second switch
            "mapViewMode = 'world'; townPrefSet('world');\n"
            "state = { settings: {} }; townAutoZoomCheck();\n"
            "state = { settings: { town_position: { city_id: 'C4' } } }; r.push(townAutoZoomCheck(), mapViewMode);\n"
            "r.push(viewSwitches);\n"
            "process.stdout.write(JSON.stringify(r));"
        )
        self.assertEqual(out, [False, True, "streets", "settlement", False, False, "world", 1])


class StaticContract(unittest.TestCase):
    def test_markup_has_the_zoom_chips_and_the_plot_card(self):
        html = INDEX.read_text(encoding="utf-8")
        for needle in (
            'id="townZoomBar"', 'data-town-zoom="city"', 'data-town-zoom="streets"', 'data-town-scale="1"',
            'id="townPlotCard"', 'id="townWalkBtn"', 'id="townGoInBtn"', 'id="townWalkStatus"',
        ):
            self.assertIn(needle, html)
        # The card sits under the canvas, outside the square map stage.
        self.assertLess(html.index('id="settlementCanvas"'), html.index('id="townPlotCard"'))
        self.assertLess(html.index('id="townPlotCard"'), html.index('id="settlementInfo"'))

    def test_walk_posts_the_engine_route_and_reads_its_view(self):
        text = APP_JS.read_text(encoding="utf-8")
        walk = _function(text, "townWalk")
        self.assertIn('fetch("/api/town/walk"', walk)
        self.assertIn("data.view", walk)
        self.assertIn("townMessage(data, res.status)", walk)
        self.assertIn("{ plot_id: found.plot.id }", _function(text, "townWalkSelected"))
        view = _function(text, "refreshTownView")
        self.assertIn("/api/town/view?", view)

    def test_context_menu_goes_through_interact_js(self):
        js = INTERACT.read_text(encoding="utf-8")
        self.assertIn('closest?.("#settlementCanvas")', js)
        self.assertIn("window.townCanvasMenu(event)", js)
        self.assertIn("openMenu: openMenuWith", js)

    def test_layout_and_look_stay_in_their_files(self):
        styles = STYLES.read_text(encoding="utf-8").replace("\r\n", "\n")
        start = styles.index("/* Town streets (docs/TownGrid.md 8)")
        block = styles[start : styles.index("/* Capped and scrolled", start)]
        for word in ("color:", "background", "border:", "#", "hsl(", "rgba("):
            self.assertNotIn(word, block)
        self.assertIn("touch-action: none", block)
        skin = SKIN.read_text(encoding="utf-8")
        self.assertIn(".townPlotCard {", skin)


if __name__ == "__main__":
    unittest.main()
