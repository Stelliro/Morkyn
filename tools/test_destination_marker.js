/**
 * Tests for static/ui/destination_marker.js (TODO n22, built but not wired).
 *
 * The marker draws the set destination on the four map views from the canvas,
 * the meta the painter stored on it and the destination record it is handed.
 * The geometry is pure and the painters take a context, so it all runs here
 * under node with `global.window = {}`, no document, a recording canvas
 * context and fake canvases. No wall clock, no random, no network.
 *
 * Exit 0 = all cases pass
 * Exit 1 = a case regressed
 * Exit 2 = harness/setup error
 */
"use strict";

const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const MODULE = path.join(ROOT, "static", "ui", "destination_marker.js");
const MODULE_NAME = "destination_marker";
const EXPORT_NAME = "MorkynDestinationMarker";

/* ------------------------------------------------------------------------
   Harness
   ------------------------------------------------------------------------ */

function assert(cond, message) {
  if (!cond) throw new Error(message || "assertion failed");
}

function assertEqual(actual, expected, message) {
  const a = JSON.stringify(actual);
  const e = JSON.stringify(expected);
  if (a !== e) throw new Error(`${message || "values differ"}: got ${a}, want ${e}`);
}

function assertClose(actual, expected, message, eps = 1e-9) {
  if (!(Math.abs(actual - expected) <= eps)) throw new Error(`${message || "numbers differ"}: got ${actual}, want ${expected}`);
}

// A 2d context that records every call and never throws.
function makeCtx() {
  const ctx = { calls: [] };
  const methods = ["save", "restore", "beginPath", "arc", "moveTo", "lineTo", "closePath", "fill", "stroke", "fillRect", "strokeRect", "setTransform", "fillText", "setLineDash"];
  methods.forEach((name) => {
    ctx[name] = (...args) => {
      ctx.calls.push({ name, args });
    };
  });
  ctx.measureText = () => ({ width: 0 });
  // Colour assignments are recorded as "set:fillStyle" / "set:strokeStyle" calls.
  ["fillStyle", "strokeStyle"].forEach((prop) => {
    let value = "";
    Object.defineProperty(ctx, prop, {
      get: () => value,
      set: (v) => {
        value = v;
        ctx.calls.push({ name: `set:${prop}`, args: [v] });
      },
    });
  });
  ctx.count = (name) => ctx.calls.filter((c) => c.name === name).length;
  ctx.colours = (prop) => ctx.calls.filter((c) => c.name === `set:${prop}`).map((c) => c.args[0]);
  return ctx;
}

function makeCanvas(width, height, extra) {
  const ctx = makeCtx();
  return Object.assign(
    {
      width,
      height,
      clientWidth: width,
      getContext: () => ctx,
      getBoundingClientRect: () => ({ width, height }),
      ctx,
    },
    extra || {},
  );
}

// The lens: cell 16, extent 5 -> an 11x11 window, 176 px, circle on.
function lensMeta(overrides) {
  return Object.assign({ minX: -5, minY: -5, cell: 16, extent: 5, mode: "local", tilePx: 16, circle: true, width: 11, height: 11 }, overrides || {});
}

function lensCanvas(metaOverrides) {
  return makeCanvas(176, 176, { _mapMeta: lensMeta(metaOverrides) });
}

const PLAYER = { x: 10, y: 10 };
const DEST_CELL = { target: { x: 12, y: 9 }, label: "the ford", enter: false, with: [], set_turn: 3 };
const DEST_CITY = { target: { x: 40, y: 41, city: "C7", location_code: "L4" }, label: "Ashbarrow", enter: true, with: ["A"], set_turn: 4 };
const DEST_PLOT = { target: { plot: "C7.1.0.12", city: "C7", x: 41, y: 40 }, label: "the smithy", enter: true, with: [], set_turn: 5, source: { kind: "quest" } };

// A settlement view: a 2x2 city C7 with world cells (40..41, 40..41).
function settlementFixture() {
  const cells = [
    { x: 40, y: 40, local: [0, 0], side: 64, known: true },
    { x: 41, y: 40, local: [1, 0], side: 64, known: true },
    { x: 40, y: 41, local: [0, 1], side: 64, known: true },
    { x: 41, y: 41, local: [1, 1], side: 64, known: false },
  ];
  const settlement = { id: "C7", name: "Ashbarrow", span: [2, 2], cells, player: { x: 40, y: 40, local: [0, 0], fine_x: 32, fine_y: 32, side: 64 } };
  const cityMeta = { ox: 8, oy: 8, unit: 100, dpr: 1, cells };
  return { settlement, cityMeta, data: { available: true, settlement } };
}

// A streets view: three cells of C7, the plot C7.1.0.12 at r = [4, 6, 3, 2] in cell (41, 40).
function townFixture() {
  const cells = [
    { cx: 40, cy: 40, local: [0, 0], side: 64, plots: [{ id: "C7.0.0.1", r: [10, 10, 4, 4], k: "house" }] },
    { cx: 41, cy: 40, local: [1, 0], side: 64, plots: [{ id: "C7.1.0.12", r: [4, 6, 3, 2], k: "shop", name: "Gedra Forge" }] },
    { cx: 40, cy: 41, local: [0, 1], side: 64, plots: [] },
  ];
  const townData = { available: true, city_id: "C7", center: { cx: 40, cy: 40 }, cells, player: { cx: 40, cy: 40, fx: 12, fy: 12, plot: "" } };
  const geo = { css: 320, cellPx: 320, originX: 100, originY: 50, center: { cx: 40, cy: 40 } };
  // townCellBox's formula with a tile of 5 CSS px (cellPx / side = 320 / 64).
  const cellBoxFn = (g, cell) => ({ x0: g.originX + (cell.cx - g.center.cx) * g.cellPx, y0: g.originY + (cell.cy - g.center.cy) * g.cellPx, tile: g.cellPx / cell.side });
  return { townData, geo, cellBoxFn, cells };
}

function isInt(v) {
  return typeof v === "number" && Number.isInteger(v);
}
function isNum(v) {
  return typeof v === "number" && Number.isFinite(v);
}

const DRAWN = ["pin", "rim", "here", "none"];
const REASONS = ["no_destination", "no_meta", "no_ctx", "off_city", "unknown_cell", "wrong_mode"];

function assertReport(r, message) {
  assert(r && typeof r === "object", `${message}: a report object`);
  assert(DRAWN.includes(r.drawn), `${message}: drawn is one of ${DRAWN.join("|")}, got ${r.drawn}`);
  const keys = Object.keys(r).sort();
  if (r.drawn === "none") {
    assertEqual(keys, ["drawn", "reason"], `${message}: none carries a reason`);
    assert(REASONS.includes(r.reason), `${message}: reason is one of ${REASONS.join("|")}, got ${r.reason}`);
  } else {
    assertEqual(keys, ["drawn"], `${message}: a drawn report has no reason`);
  }
}

/* ------------------------------------------------------------------------
   Cases
   ------------------------------------------------------------------------ */

const CASES = [];
function test(name, fn) {
  CASES.push({ name, fn });
}

test("test_module_is_a_leaf", () => {
  const source = fs.readFileSync(MODULE, "utf8");
  const required = [
    "Status: built, not wired (TODO n22",
    "Wiring (not done):",
    "Turn on:",
    "Tests: tools/test_destination_marker.js",
  ];
  required.forEach((line) => assert(source.includes(line), `header line missing: ${line}`));
  // Nothing under app/ or static/ loads or calls the module: no script tag or
  // load path naming the file, no use of its export. A Python docstring that
  // mentions the file by name is prose, not a load, so a .py hit counts only
  // when it names the export or the load path.
  const hits = [];
  const walk = (dir) => {
    fs.readdirSync(dir, { withFileTypes: true }).forEach((entry) => {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === "__pycache__" || entry.name === "node_modules") return;
        walk(full);
        return;
      }
      if (!/\.(py|js|html|css|md|txt|json)$/.test(entry.name)) return;
      if (full === MODULE) return;
      const text = fs.readFileSync(full, "utf8");
      const usesExport = text.includes(EXPORT_NAME);
      const loadsFile = text.includes(`ui/${MODULE_NAME}.js`) || (text.includes("require(") && text.includes(`${MODULE_NAME}.js`));
      const namesFile = /\.(js|html|css)$/.test(entry.name) && text.includes(MODULE_NAME);
      if (usesExport || loadsFile || namesFile) hits.push(path.relative(ROOT, full));
    });
  };
  walk(path.join(ROOT, "app"));
  walk(path.join(ROOT, "static"));
  assertEqual(hits, [], "files under app/ or static/ that load or call the module");
  ["index.html", "popout.html"].forEach((page) => {
    const text = fs.readFileSync(path.join(ROOT, "static", page), "utf8");
    assert(!text.includes(`${MODULE_NAME}.js`), `static/${page} loads the module`);
  });
});

test("module_loads_without_document", () => {
  assert(typeof document === "undefined", "the harness must not define document");
  const api = window[EXPORT_NAME];
  const methods = [
    "isSet",
    "label",
    "targetKind",
    "plotLocal",
    "worldPoint",
    "rimPoint",
    "cityPoint",
    "streetsBox",
    "paintFlag",
    "paintRimArrow",
    "paintHereRing",
    "paintBox",
    "drawWorld",
    "drawSettlement",
    "drawStreets",
    "draw",
  ];
  methods.forEach((m) => assert(typeof api[m] === "function", `export lacks ${m}()`));
  assert(api.STYLE && typeof api.STYLE === "object", "STYLE missing");
  assert(typeof api.TARGET_KIND === "function", "TARGET_KIND missing");
  assertEqual(Object.keys(window).sort(), [EXPORT_NAME], "the module set more than its one export on window");
});

test("style_matches_the_design_table", () => {
  const s = window[EXPORT_NAME].STYLE;
  assertEqual(s.fill, ["--thread-bright", "#ece4fb"], "fill");
  assertEqual(s.accent, ["--moon", "#d4566a"], "accent");
  assertEqual(s.ink, "rgba(0,0,0,0.85)", "ink");
  assertEqual(s.alpha, 0.95, "alpha");
  assertEqual(s.poleFrac, 0.62, "poleFrac");
  assertEqual(s.pennantFrac, 0.34, "pennantFrac");
  assertEqual(s.minPx, 5, "minPx");
  assertEqual(s.rimBlipFrac, 8, "rimBlipFrac");
  assertEqual(s.hereRingFrac, 0.42, "hereRingFrac");
  assertEqual(s.streetsPad, 1.5, "streetsPad");
  assertEqual(s.cellMarkTiles, 3, "cellMarkTiles");
  assertEqual(Object.keys(s).length, 11, "no extra style keys");
});

test("targetKind_and_plotLocal", () => {
  const api = window[EXPORT_NAME];
  assertEqual(api.targetKind(DEST_PLOT.target), "plot", "plot form");
  assertEqual(api.targetKind(DEST_CITY.target), "city", "city form");
  assertEqual(api.targetKind(DEST_CELL.target), "cell", "cell form");
  assertEqual(api.targetKind({}), "", "empty");
  assertEqual(api.targetKind(null), "", "null");
  assertEqual(api.targetKind({ x: "a", y: 2 }), "", "non-numeric x");
  assertEqual(api.TARGET_KIND(DEST_CELL.target), "cell", "TARGET_KIND is the same rule");
  assertEqual(api.plotLocal("C7.1.0.12"), [1, 0], "plot id to local");
  assertEqual(api.plotLocal("S3.12.7.0"), [12, 7], "two-digit local");
  assertEqual(api.plotLocal("junk"), null, "junk");
  assertEqual(api.plotLocal("C7.a.0.1"), null, "non-numeric part");
  assertEqual(api.plotLocal("C7.1.0"), null, "three parts");
  assertEqual(api.plotLocal(""), null, "empty");
  assertEqual(api.plotLocal(null), null, "null");
});

test("isSet_and_label_accept_all_three_target_forms", () => {
  const api = window[EXPORT_NAME];
  [DEST_CELL, DEST_CITY, DEST_PLOT].forEach((d) => assert(api.isSet(d), `${d.label} is set`));
  assert(!api.isSet(null), "null");
  assert(!api.isSet({}), "no target");
  assert(!api.isSet({ target: "x,y" }), "a string target");
  assert(!api.isSet({ target: {} }), "an empty target");
  assertEqual(api.label(DEST_CELL), "the ford", "label");
  assertEqual(api.label({ target: { x: 1, y: 1 } }), "Destination", "fallback label");
  assertEqual(api.label({ target: { x: 1, y: 1 }, label: "   " }), "Destination", "blank label");
  assertEqual(api.label(null), "Destination", "null");
});

test("worldPoint_local_mode_offsets_by_player", () => {
  const api = window[EXPORT_NAME];
  const p = api.worldPoint({ minX: -5, minY: -5, cell: 16 }, { x: 12, y: 9 }, PLAYER, "local");
  assertEqual(p, { px: 112, py: 64, relX: 2, relY: -1, inside: true }, "local point");
  assertEqual(Object.keys(p).sort(), ["inside", "px", "py", "relX", "relY"], "WorldPoint keys");
  assert(isNum(p.px) && isNum(p.py) && isNum(p.relX) && isNum(p.relY) && typeof p.inside === "boolean", "WorldPoint types");
  assertEqual(api.worldPoint(null, { x: 1, y: 1 }, PLAYER, "local"), null, "no meta");
  assertEqual(api.worldPoint({ minX: 0, minY: 0, cell: 16 }, null, PLAYER, "local"), null, "no target");
  assertEqual(api.worldPoint({ minX: 0, minY: 0, cell: 16 }, { plot: "C7.1.0.12", city: "C7" }, PLAYER, "local"), null, "a plot with no cell");
  assertEqual(api.worldPoint({ minX: 0, minY: 0 }, { x: 1, y: 1 }, PLAYER, "local"), null, "meta without cell");
  // Above or left of the window is not inside.
  const out = api.worldPoint({ minX: -5, minY: -5, cell: 16 }, { x: 3, y: 10 }, PLAYER, "local");
  assertEqual([out.relX, out.px, out.inside], [-7, -32, false], "left of the window");
});

test("worldPoint_full_mode_absolute", () => {
  const api = window[EXPORT_NAME];
  const p = api.worldPoint({ minX: 0, minY: 0, cell: 8, mode: "full", circle: false, width: 64, height: 64 }, { x: 12, y: 9 }, PLAYER, "full");
  assertEqual(p, { px: 96, py: 72, relX: 12, relY: 9, inside: true }, "full point ignores the player");
  const far = api.worldPoint({ minX: 0, minY: 0, cell: 8, mode: "full", circle: false, width: 64, height: 64 }, { x: 64, y: 9 }, PLAYER, "full");
  assertEqual([far.px, far.inside], [512, false], "past the right edge in tiles");
  const sized = api.worldPoint({ minX: 0, minY: 0, cell: 8 }, { x: 12, y: 9 }, PLAYER, "full", { width: 90, height: 90 });
  assertEqual(sized.inside, false, "an explicit px size wins over the meta");
});

test("worldPoint_outside_circle_is_not_inside", () => {
  const api = window[EXPORT_NAME];
  // A 160 px lens (10 tiles of 16): seven cells out is past the edge.
  const meta = { minX: -5, minY: -5, cell: 16, circle: true, width: 10, height: 10 };
  const far = api.worldPoint(meta, { x: 17, y: 10 }, PLAYER, "local");
  assertEqual([far.relX, far.px, far.inside], [7, 192, false], "seven cells out");
  // Inside the square but outside the circle (the corner).
  const corner = api.worldPoint(meta, { x: 14, y: 14 }, PLAYER, "local");
  assertEqual([corner.px, corner.py, corner.inside], [144, 144, false], "the corner is outside the circle");
  // Straight along an axis within the radius is inside.
  const axis = api.worldPoint(meta, { x: 14, y: 10 }, PLAYER, "local");
  assertEqual([axis.px, axis.inside], [144, true], "four cells east is inside");
  // The same cell on a square window (circle off) is inside.
  const square = api.worldPoint(Object.assign({}, meta, { circle: false }), { x: 14, y: 14 }, PLAYER, "local");
  assertEqual(square.inside, true, "circle off: the corner is inside");
});

test("rimPoint_angle_matches_direction", () => {
  const api = window[EXPORT_NAME];
  const canvas = lensCanvas();
  const r = api.rimPoint(canvas, canvas._mapMeta, 0, -3);
  assertEqual(Object.keys(r).sort(), ["angle", "px", "py"], "RimPoint keys");
  assertClose(r.angle, -Math.PI / 2, "north is -pi/2");
  assert(r.py < canvas.height / 2, "north sits above the centre");
  assertClose(r.px, canvas.width / 2, "north sits on the vertical axis", 1e-6);
  assert(r.py >= 0 && r.py <= canvas.height, "on the canvas");
  const east = api.rimPoint(canvas, canvas._mapMeta, 5, 0);
  assertClose(east.angle, 0, "east is 0");
  assert(east.px > canvas.width / 2, "east sits right of the centre");
  // The rim radius copies paintTileGrid: blip = max(6, round(8 * width / shown)), rimR = circleR - blip - 2.
  const blip = Math.max(6, Math.round((8 * canvas.width) / Math.max(80, canvas.clientWidth)));
  const rimR = Math.max(blip + 2, canvas.width / 2 - 1 - blip - 2);
  assertClose(east.px, canvas.width / 2 + rimR, "rim radius", 1e-6);
  // The Large map clamps into its edge instead of a circle.
  const full = makeCanvas(64, 64, { _mapMeta: { minX: 0, minY: 0, cell: 8, circle: false, mode: "full", width: 8, height: 8 } });
  const clamped = api.rimPoint(full, full._mapMeta, 20, 2);
  assert(clamped.px < 64 && clamped.px > 32, "clamped inside the right edge");
  assert(clamped.angle > -Math.PI / 2 && clamped.angle < Math.PI / 2, "pointing out to the right");
});

test("drawWorld_pin_rim_here_none", () => {
  const api = window[EXPORT_NAME];
  const pin = lensCanvas();
  const r1 = api.drawWorld(pin, DEST_CELL, PLAYER, "local");
  assertEqual(r1, { drawn: "pin" }, "a cell in the window is a pin");
  assert(pin.ctx.count("save") > 0, "the flag painted something");
  assertEqual(pin.ctx.count("save"), pin.ctx.count("restore"), "save and restore balance (pin)");

  const rim = lensCanvas();
  const r2 = api.drawWorld(rim, { target: { x: 10, y: 1 }, label: "far north" }, PLAYER, "local");
  assertEqual(r2, { drawn: "rim" }, "a cell off the window is a rim arrow");
  assertEqual(rim.ctx.count("save"), rim.ctx.count("restore"), "save and restore balance (rim)");
  const arrowArc = rim.ctx.calls.find((c) => c.name === "arc");
  assert(arrowArc && arrowArc.args[1] < rim.height / 2, "the arrow sits in the top half");

  const here = lensCanvas();
  const r3 = api.drawWorld(here, { target: { x: 10, y: 10 }, label: "here" }, PLAYER, "local");
  assertEqual(r3, { drawn: "here" }, "the player's own cell is a ring");
  assertEqual(here.ctx.count("save"), here.ctx.count("restore"), "save and restore balance (here)");
  const ringArc = here.ctx.calls.find((c) => c.name === "arc");
  assertClose(ringArc.args[0], 88, "ring centred on the player tile x");
  assertClose(ringArc.args[1], 88, "ring centred on the player tile y");

  const none = lensCanvas();
  assertEqual(api.drawWorld(none, null, PLAYER, "local"), { drawn: "none", reason: "no_destination" }, "null dest");
  assertEqual(api.drawWorld(none, { label: "x" }, PLAYER, "local"), { drawn: "none", reason: "no_destination" }, "dest without target");
  assertEqual(none.ctx.calls.length, 0, "nothing painted for none");
  assertEqual(api.drawWorld(makeCanvas(176, 176), DEST_CELL, PLAYER, "local"), { drawn: "none", reason: "no_meta" }, "no _mapMeta");
  assertEqual(api.drawWorld(null, DEST_CELL, PLAYER, "local"), { drawn: "none", reason: "no_meta" }, "no canvas");
  assertEqual(api.drawWorld(lensCanvas(), DEST_CELL, PLAYER, "settlement"), { drawn: "none", reason: "wrong_mode" }, "wrong mode");
  const noCtx = lensCanvas();
  noCtx.getContext = () => null;
  assertEqual(api.drawWorld(noCtx, DEST_CELL, PLAYER, "local"), { drawn: "none", reason: "no_ctx" }, "getContext null");
  const throwing = lensCanvas();
  throwing.getContext = () => {
    throw new Error("no 2d");
  };
  assertEqual(api.drawWorld(throwing, DEST_CELL, PLAYER, "local"), { drawn: "none", reason: "no_ctx" }, "getContext throws");
  assertEqual(api.drawWorld(lensCanvas(), { target: { plot: "C7.1.0.12", city: "C7" } }, PLAYER, "local"), { drawn: "none", reason: "unknown_cell" }, "a plot with no cell on the world map");

  // Full mode: absolute coordinates; the plot form carries x/y so it pins too.
  const full = makeCanvas(400, 400, { _mapMeta: { minX: 0, minY: 0, cell: 8, circle: false, mode: "full", width: 50, height: 50 } });
  assertEqual(api.drawWorld(full, DEST_PLOT, PLAYER, "full"), { drawn: "pin" }, "plot form pins on the Large map");
  assertEqual(api.drawWorld(full, { target: { x: 90, y: 2 } }, PLAYER, "full"), { drawn: "rim" }, "off the Large map is a rim arrow");
  assertEqual(full.ctx.count("save"), full.ctx.count("restore"), "save and restore balance (full)");
});

test("cityPoint_finds_cell_by_xy_and_by_plot", () => {
  const api = window[EXPORT_NAME];
  const f = settlementFixture();
  const byXy = api.cityPoint(f.cityMeta, f.settlement, DEST_CITY.target);
  assertEqual(byXy, { px: 58, py: 158, cellX: 40, cellY: 41, unit: 100 }, "cell (40, 41) is local [0, 1]");
  assertEqual(Object.keys(byXy).sort(), ["cellX", "cellY", "px", "py", "unit"], "CityPoint keys");
  const byPlot = api.cityPoint(f.cityMeta, f.settlement, { plot: "C7.1.0.12", city: "C7" });
  assertEqual(byPlot, { px: 158, py: 58, cellX: 41, cellY: 40, unit: 100 }, "plot id resolves through plotLocal");
  assertEqual(api.cityPoint(f.cityMeta, f.settlement, { x: 40, y: 40, city: "C9" }), null, "wrong city");
  assertEqual(api.cityPoint(f.cityMeta, f.settlement, { x: 40, y: 40 }), null, "a bare world cell names no city");
  assertEqual(api.cityPoint(f.cityMeta, f.settlement, { x: 45, y: 45, city: "C7" }), null, "a cell outside the city");
  assertEqual(api.cityPoint(f.cityMeta, f.settlement, { plot: "C7.5.5.1", city: "C7" }), null, "a plot in no drawn cell");
  assertEqual(api.cityPoint(null, f.settlement, DEST_CITY.target), null, "no meta");
  assertEqual(api.cityPoint(f.cityMeta, null, DEST_CITY.target), null, "no settlement");
  assertEqual(api.cityPoint({ ox: 0, oy: 0, unit: 0, cells: f.settlement.cells }, f.settlement, DEST_CITY.target), null, "unit 0");
});

test("drawSettlement_reports", () => {
  const api = window[EXPORT_NAME];
  const f = settlementFixture();
  const pin = makeCanvas(216, 216, { _cityMeta: f.cityMeta });
  assertEqual(api.drawSettlement(pin, DEST_CITY, f.data), { drawn: "pin" }, "a city cell is a pin");
  assertEqual(pin.ctx.count("save"), pin.ctx.count("restore"), "save and restore balance");
  const here = makeCanvas(216, 216, { _cityMeta: f.cityMeta });
  assertEqual(api.drawSettlement(here, { target: { x: 40, y: 40, city: "C7" } }, f.data), { drawn: "here" }, "the player's cell is a ring");
  const off = makeCanvas(216, 216, { _cityMeta: f.cityMeta });
  assertEqual(api.drawSettlement(off, { target: { x: 40, y: 40, city: "C9" } }, f.data), { drawn: "none", reason: "off_city" }, "another city");
  assertEqual(api.drawSettlement(off, DEST_CELL, f.data), { drawn: "none", reason: "off_city" }, "a wild cell is off the city");
  assertEqual(off.ctx.calls.length, 0, "nothing painted when off the city");
  assertEqual(api.drawSettlement(off, null, f.data), { drawn: "none", reason: "no_destination" }, "null dest");
  assertEqual(api.drawSettlement(makeCanvas(216, 216), DEST_CITY, f.data), { drawn: "none", reason: "no_meta" }, "no _cityMeta");
  assertEqual(api.drawSettlement(off, DEST_CITY, { available: false }), { drawn: "none", reason: "no_meta" }, "no settlement record");
  const noCtx = makeCanvas(216, 216, { _cityMeta: f.cityMeta });
  noCtx.getContext = () => null;
  assertEqual(api.drawSettlement(noCtx, DEST_CITY, f.data), { drawn: "none", reason: "no_ctx" }, "getContext null");
});

test("streetsBox_plot_rect_and_cell_centre", () => {
  const api = window[EXPORT_NAME];
  const t = townFixture();
  const plot = api.streetsBox(t.geo, t.townData, DEST_PLOT.target, t.cellBoxFn);
  // Cell (41, 40) sits one cell right of the centre: box origin (420, 50), tile 5; r = [4, 6, 3, 2].
  assertEqual(plot, { x0: 440, y0: 80, w: 15, h: 10, tile: 5, kind: "plot" }, "plot rect from r");
  assertEqual(Object.keys(plot).sort(), ["h", "kind", "tile", "w", "x0", "y0"], "StreetsBox keys");
  // The design's numbers: a box at (100, 50) with tile 5 gives (120, 80, 15, 10).
  const fixedBox = () => ({ x0: 100, y0: 50, tile: 5 });
  assertEqual(api.streetsBox(t.geo, t.townData, DEST_PLOT.target, fixedBox), { x0: 120, y0: 80, w: 15, h: 10, tile: 5, kind: "plot" }, "design example");
  // A plot target with no x/y finds its cell through the plot list.
  assertEqual(api.streetsBox(t.geo, t.townData, { plot: "C7.1.0.12", city: "C7" }, fixedBox).kind, "plot", "plot without x/y");
  // A cell target: a 3x3-tile square at the cell centre (cellPx 320 -> centre at +160).
  const cell = api.streetsBox(t.geo, t.townData, { x: 40, y: 41, city: "C7" }, fixedBox);
  assertEqual(cell, { x0: 252.5, y0: 202.5, w: 15, h: 15, tile: 5, kind: "cell" }, "cell centre square");
  // A plot id that is not in the cell falls back to the cell centre.
  const missing = api.streetsBox(t.geo, t.townData, { plot: "C7.0.1.99", city: "C7", x: 40, y: 41 }, fixedBox);
  assertEqual(missing.kind, "cell", "unknown plot in a known cell");
  assertEqual(api.streetsBox(t.geo, t.townData, { x: 48, y: 48, city: "C7" }, fixedBox), null, "a cell not in the view");
  assertEqual(api.streetsBox(t.geo, t.townData, { x: 40, y: 40, city: "C9" }, fixedBox), null, "another town");
  assertEqual(api.streetsBox(t.geo, t.townData, { plot: "C9.0.0.1", city: "C9" }, fixedBox), null, "a plot of another town");
  assertEqual(api.streetsBox(t.geo, t.townData, DEST_PLOT.target, null), null, "no cellBoxFn");
  assertEqual(api.streetsBox(null, t.townData, DEST_PLOT.target, fixedBox), null, "no geo");
  assertEqual(api.streetsBox(t.geo, t.townData, DEST_PLOT.target, () => null), null, "cellBoxFn returns nothing");
  assertEqual(
    api.streetsBox(t.geo, t.townData, DEST_PLOT.target, () => {
      throw new Error("boom");
    }),
    null,
    "cellBoxFn throws",
  );
});

test("drawStreets_reports", () => {
  const api = window[EXPORT_NAME];
  const t = townFixture();
  const pin = makeCanvas(320, 320);
  assertEqual(api.drawStreets(pin, DEST_PLOT, t.townData, t.geo, t.cellBoxFn), { drawn: "pin" }, "a plot is a box");
  assert(pin.ctx.count("strokeRect") >= 2, "the box is stroked");
  assertEqual(pin.ctx.count("save"), pin.ctx.count("restore"), "save and restore balance");
  const hereCell = makeCanvas(320, 320);
  assertEqual(api.drawStreets(hereCell, { target: { x: 40, y: 40, city: "C7" } }, t.townData, t.geo, t.cellBoxFn), { drawn: "here" }, "the player's cell is a ring");
  const herePlot = makeCanvas(320, 320);
  const inPlot = Object.assign({}, t.townData, { player: { cx: 41, cy: 40, fx: 5, fy: 7, plot: "C7.1.0.12" } });
  assertEqual(api.drawStreets(herePlot, DEST_PLOT, inPlot, t.geo, t.cellBoxFn), { drawn: "here" }, "inside the target plot is a ring");
  const sameCellOtherPlot = Object.assign({}, t.townData, { player: { cx: 41, cy: 40, fx: 30, fy: 30, plot: "" } });
  assertEqual(api.drawStreets(makeCanvas(320, 320), DEST_PLOT, sameCellOtherPlot, t.geo, t.cellBoxFn), { drawn: "pin" }, "same cell, not in the plot: still a box");
  const unknown = makeCanvas(320, 320);
  assertEqual(api.drawStreets(unknown, { target: { x: 48, y: 48, city: "C7" } }, t.townData, t.geo, t.cellBoxFn), { drawn: "none", reason: "unknown_cell" }, "a cell not drawn");
  assertEqual(unknown.ctx.calls.length, 0, "nothing painted for an unknown cell");
  assertEqual(api.drawStreets(unknown, null, t.townData, t.geo, t.cellBoxFn), { drawn: "none", reason: "no_destination" }, "null dest");
  assertEqual(api.drawStreets(unknown, DEST_PLOT, null, t.geo, t.cellBoxFn), { drawn: "none", reason: "no_meta" }, "no townData");
  assertEqual(api.drawStreets(unknown, DEST_PLOT, t.townData, null, t.cellBoxFn), { drawn: "none", reason: "no_meta" }, "no geo");
  assertEqual(api.drawStreets(unknown, DEST_PLOT, t.townData, t.geo, null), { drawn: "none", reason: "no_meta" }, "no cellBoxFn");
  const noCtx = makeCanvas(320, 320);
  noCtx.getContext = () => null;
  assertEqual(api.drawStreets(noCtx, DEST_PLOT, t.townData, t.geo, t.cellBoxFn), { drawn: "none", reason: "no_ctx" }, "getContext null");
});

test("draw_without_globals_degrades", () => {
  const api = window[EXPORT_NAME];
  assert(typeof settlementData === "undefined" && typeof townData === "undefined", "the harness defines no app.js globals");
  const f = settlementFixture();
  const canvas = makeCanvas(216, 216, { _cityMeta: f.cityMeta });
  assertEqual(api.draw(canvas, DEST_CITY, null, "settlement"), { drawn: "none", reason: "no_meta" }, "settlement without settlementData");
  assertEqual(api.draw(makeCanvas(320, 320), DEST_PLOT, null, "streets"), { drawn: "none", reason: "no_meta" }, "streets without townData");
  assertEqual(api.draw(canvas, null, null, "settlement"), { drawn: "none", reason: "no_destination" }, "no destination wins over no globals");
  assertEqual(api.draw(lensCanvas(), DEST_CELL, PLAYER, "orbit"), { drawn: "none", reason: "wrong_mode" }, "an unknown mode");
  assertEqual(api.draw(lensCanvas(), DEST_CELL, PLAYER, "local"), { drawn: "pin" }, "local dispatches to drawWorld");
  assertEqual(api.draw(lensCanvas(), { target: { x: 10, y: 1 } }, PLAYER, "local"), { drawn: "rim" }, "rim through draw");
  const full = makeCanvas(400, 400, { _mapMeta: { minX: 0, minY: 0, cell: 8, circle: false, mode: "full", width: 50, height: 50 } });
  assertEqual(api.draw(full, DEST_CELL, PLAYER, "full"), { drawn: "pin" }, "full dispatches to drawWorld");
  assertEqual(canvas.ctx.calls.length, 0, "nothing painted when the globals are missing");
});

test("draw_with_page_globals_uses_them", () => {
  // The two town modes read settlementData / townData / townGeometry /
  // townCellBox by bare name. The node harness fakes them on globalThis for
  // this one case and removes them after, so the leaf stays leaf.
  const api = window[EXPORT_NAME];
  const f = settlementFixture();
  const t = townFixture();
  const g = globalThis;
  try {
    g.settlementData = f.data;
    g.townData = t.townData;
    g.townGeometry = () => t.geo;
    g.townCellBox = t.cellBoxFn;
    let tokenHits = 0;
    g.cssToken = (name, fallback) => {
      tokenHits += 1;
      return name === "--moon" ? "#123456" : fallback;
    };
    const sCanvas = makeCanvas(216, 216, { _cityMeta: f.cityMeta });
    assertEqual(api.draw(sCanvas, DEST_CITY, null, "settlement"), { drawn: "pin" }, "settlement through the page global");
    const tCanvas = makeCanvas(320, 320);
    assertEqual(api.draw(tCanvas, DEST_PLOT, null, "streets"), { drawn: "pin" }, "streets through the page globals");
    // cssToken was consulted for the accent colour and its answer reached the context.
    const fills = tCanvas.ctx.calls.filter((c) => c.name === "fill");
    assert(fills.length > 0, "the corner flag filled");
    assert(tokenHits > 0, "cssToken was called");
    assert(tCanvas.ctx.colours("fillStyle").includes("#123456"), "the token colour was set as fillStyle");
    assert(sCanvas.ctx.colours("fillStyle").includes("#123456"), "the settlement flag used the token colour too");
    g.townGeometry = () => {
      throw new Error("no canvas");
    };
    assertEqual(api.draw(tCanvas, DEST_PLOT, null, "streets"), { drawn: "none", reason: "no_meta" }, "townGeometry throwing is no_meta");
  } finally {
    delete g.settlementData;
    delete g.townData;
    delete g.townGeometry;
    delete g.townCellBox;
    delete g.cssToken;
  }
  assert(typeof settlementData === "undefined", "the fake global was removed");
});

test("draw_never_mutates_its_inputs", () => {
  // The browser analogue of the "no foreign writes" test: draw() changes
  // nothing it was handed and sets nothing new on window.
  const api = window[EXPORT_NAME];
  const canvas = lensCanvas();
  const metaBefore = JSON.stringify(canvas._mapMeta);
  const destBefore = JSON.stringify(DEST_CELL);
  const playerBefore = JSON.stringify(PLAYER);
  const canvasKeys = Object.keys(canvas).sort();
  api.draw(canvas, DEST_CELL, PLAYER, "local");
  api.draw(canvas, { target: { x: 10, y: 1 } }, PLAYER, "local");
  const f = settlementFixture();
  const sBefore = JSON.stringify(f.data);
  const sCanvas = makeCanvas(216, 216, { _cityMeta: f.cityMeta });
  api.drawSettlement(sCanvas, DEST_CITY, f.data);
  const t = townFixture();
  const tBefore = JSON.stringify(t.townData);
  api.drawStreets(makeCanvas(320, 320), DEST_PLOT, t.townData, t.geo, t.cellBoxFn);
  assertEqual(JSON.stringify(canvas._mapMeta), metaBefore, "_mapMeta untouched");
  assertEqual(JSON.stringify(DEST_CELL), destBefore, "dest untouched");
  assertEqual(JSON.stringify(PLAYER), playerBefore, "player untouched");
  assertEqual(Object.keys(canvas).sort(), canvasKeys, "no new keys on the canvas");
  assertEqual(JSON.stringify(f.data), sBefore, "settlement data untouched");
  assertEqual(JSON.stringify(t.townData), tBefore, "town data untouched");
  assertEqual(Object.keys(window).sort(), [EXPORT_NAME], "window still holds only the export");
});

test("painters_balance_save_restore_and_honour_style", () => {
  const api = window[EXPORT_NAME];
  const ctx = makeCtx();
  api.paintFlag(ctx, 0, 0, 16);
  api.paintRimArrow(ctx, 50, 50, Math.PI / 4, 8);
  api.paintHereRing(ctx, 0, 0, 16);
  api.paintBox(ctx, { x0: 10, y0: 10, w: 20, h: 10, tile: 5, kind: "plot" });
  api.paintBox(ctx, { x0: 10, y0: 10, w: 20, h: 10, tile: 5, kind: "cell" });
  assertEqual(ctx.count("save"), ctx.count("restore"), "every painter restores");
  assert(ctx.count("save") >= 5, "each painter saved once");
  // No cssToken on this page: the accent falls back to the table's colour.
  assert(typeof cssToken === "undefined", "no cssToken in the harness");
  assert(ctx.colours("fillStyle").includes(api.STYLE.accent[1]), "fallback accent set as fillStyle");
  assert(ctx.colours("strokeStyle").includes(api.STYLE.accent[1]), "fallback accent set as strokeStyle");
  // The pole never shrinks below minPx: a 2 px cell still draws a 5 px pole.
  const tiny = makeCtx();
  api.paintFlag(tiny, 0, 0, 2);
  const line = tiny.calls.filter((c) => c.name === "lineTo")[0];
  const move = tiny.calls.filter((c) => c.name === "moveTo")[0];
  assertClose(move.args[1] - line.args[1], api.STYLE.minPx, "pole height is minPx");
  // The box is padded by streetsPad on every side.
  const padded = makeCtx();
  api.paintBox(padded, { x0: 10, y0: 10, w: 20, h: 10, tile: 5, kind: "cell" });
  const rect = padded.calls.find((c) => c.name === "strokeRect");
  assertEqual(rect.args, [8.5, 8.5, 23, 13], "streetsPad 1.5 on each side");
  // A style override is merged over the table, not into it.
  const styled = makeCtx();
  api.paintHereRing(styled, 0, 0, 100, { hereRingFrac: 0.1 });
  assertClose(styled.calls.find((c) => c.name === "arc").args[2], 10, "override radius");
  assertEqual(api.STYLE.hereRingFrac, 0.42, "STYLE unchanged by an override");
  // Painters without a context do nothing and never throw.
  api.paintFlag(null, 0, 0, 16);
  api.paintBox(makeCtx(), null);
  // A context missing a method does not break the painter's save/restore.
  const broken = makeCtx();
  delete broken.arc;
  api.paintHereRing(broken, 0, 0, 16);
  assertEqual(broken.count("save"), broken.count("restore"), "restore after a failed method");
});

test("junk_inputs_never_throw", () => {
  const api = window[EXPORT_NAME];
  const junk = [undefined, null, 0, "", "x", [], {}, { target: 5 }, { target: { x: "a" } }, { target: { plot: 7 } }, { target: { city: "C7", x: null, y: null } }, { target: { x: "12", y: "9" } }];
  const modes = ["local", "full", "settlement", "streets", "", null, 42];
  junk.forEach((d) => {
    modes.forEach((m) => {
      const r = api.draw(lensCanvas(), d, PLAYER, m);
      assertReport(r, `draw(${JSON.stringify(d)}, ${JSON.stringify(m)})`);
      assertEqual(r.drawn, "none", "junk never draws");
    });
    assertReport(api.drawWorld(undefined, d, undefined, "local"), "drawWorld junk");
    assertReport(api.drawSettlement(undefined, d, undefined), "drawSettlement junk");
    assertReport(api.drawStreets(undefined, d, undefined, undefined, undefined), "drawStreets junk");
    assert(typeof api.isSet(d) === "boolean", "isSet returns a boolean");
    assert(typeof api.label(d) === "string", "label returns a string");
    assert(typeof api.targetKind(d && d.target) === "string", "targetKind returns a string");
  });
  assertEqual(api.worldPoint({ cell: 16 }, { x: 1, y: 1 }, null, "local"), { px: 16, py: 16, relX: 1, relY: 1, inside: true }, "no player: offsets from 0");
  assertEqual(api.worldPoint({ minX: 0, minY: 0, cell: 16 }, { city: "C7", x: null, y: null }, null, "full"), null, "null coordinates name no cell");
  assertEqual(api.drawWorld(lensCanvas(), { target: { city: "C7", x: null, y: null } }, PLAYER, "local"), { drawn: "none", reason: "unknown_cell" }, "a city target with null coordinates draws nothing");
  assertEqual(api.worldPoint({ cell: -1 }, { x: 1, y: 1 }, null, "local"), null, "a negative cell is no meta");
  const r = api.rimPoint({}, {}, NaN, NaN);
  assert(isNum(r.px) && isNum(r.py) && isNum(r.angle), "rimPoint on an empty canvas gives numbers");
});

test("report_shapes_are_pinned", () => {
  const api = window[EXPORT_NAME];
  const f = settlementFixture();
  const t = townFixture();
  const reports = [
    api.drawWorld(lensCanvas(), DEST_CELL, PLAYER, "local"),
    api.drawWorld(lensCanvas(), { target: { x: 10, y: 1 } }, PLAYER, "local"),
    api.drawWorld(lensCanvas(), { target: { x: 10, y: 10 } }, PLAYER, "local"),
    api.drawWorld(lensCanvas(), null, PLAYER, "local"),
    api.drawSettlement(makeCanvas(216, 216, { _cityMeta: f.cityMeta }), DEST_CITY, f.data),
    api.drawSettlement(makeCanvas(216, 216, { _cityMeta: f.cityMeta }), DEST_CELL, f.data),
    api.drawStreets(makeCanvas(320, 320), DEST_PLOT, t.townData, t.geo, t.cellBoxFn),
    api.drawStreets(makeCanvas(320, 320), { target: { x: 48, y: 48, city: "C7" } }, t.townData, t.geo, t.cellBoxFn),
  ];
  reports.forEach((r, i) => assertReport(r, `report ${i}`));
  assertEqual(
    reports.map((r) => r.drawn),
    ["pin", "rim", "here", "none", "pin", "none", "pin", "none"],
    "the four drawn values appear",
  );
  // The three Target forms (contracts 1.17) are each accepted by isSet and
  // classified by targetKind; the ones with a cell give an integer world cell.
  [DEST_CELL, DEST_CITY, DEST_PLOT].forEach((d) => {
    const p = api.worldPoint({ minX: 0, minY: 0, cell: 1 }, d.target, { x: 0, y: 0 }, "full");
    assert(p && isInt(p.relX) && isInt(p.relY), `${d.label}: integer world cell`);
  });
});

/* ------------------------------------------------------------------------
   Runner
   ------------------------------------------------------------------------ */

function main() {
  try {
    global.window = {};
    require(MODULE);
  } catch (err) {
    console.error("HARNESS ERROR: module failed to load:", err && err.message);
    return 2;
  }
  if (!window[EXPORT_NAME]) {
    console.error(`HARNESS ERROR: window.${EXPORT_NAME} not set`);
    return 2;
  }
  const failures = [];
  CASES.forEach(({ name, fn }) => {
    try {
      fn();
    } catch (err) {
      failures.push(`${name}: ${err && err.message}`);
    }
  });
  if (failures.length) {
    console.error("FAIL");
    failures.forEach((f) => console.error("  -", f));
    return 1;
  }
  console.log(`PASS  destination_marker: ${CASES.length} cases`);
  return 0;
}

process.exit(main());
